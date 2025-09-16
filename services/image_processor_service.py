"""
Serviço de Processamento de Imagens - Adaptado de image_processing_pipeline.py
"""

import os
import io
import base64
import mimetypes
import requests
import logging
import asyncio
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw, ImageChops
from datetime import datetime
import dashscope
from dashscope import MultiModalConversation
from dotenv import load_dotenv
import uuid
import tempfile
from collections import deque
class QuotaExceededError(Exception):
    """Erro lançado quando a cota gratuita é excedida."""


logger = logging.getLogger(__name__)

class ImageProcessorService:
    def __init__(self):
        """Inicializa o processador de imagens"""
        load_dotenv()
        
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        # Flag: salvar arquivos finais/intermediários? Default: False (modo consulta)
        self.save_files = os.getenv("SAVE_OUTPUT_FILES", "false").lower() in ("1", "true", "yes")
        
        # Limites (podem ser customizados por ENV)
        self.rps_limit = int(os.getenv("DASHSCOPE_RPS_LIMIT", "2"))
        self.max_concurrent = int(os.getenv("DASHSCOPE_MAX_CONCURRENT", "2"))
        self.free_quota = int(os.getenv("DASHSCOPE_FREE_QUOTA", "100"))
        
        # Concurrency control
        self._concurrency_semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # Simple RPS limiter (tokenized by timestamps in a 1s window)
        self._rps_lock = asyncio.Lock()
        self._submission_window = deque()  # stores time.monotonic()
        
        # Quota tracking (daily reset)
        self._quota_lock = asyncio.Lock()
        self._quota_file = Path("logs") / "qwen_usage.json"
        self._quota_file.parent.mkdir(exist_ok=True)
        self._quota_date = datetime.now().date().isoformat()
        self._quota_count = 0
        self._load_quota_state()
        
        if self.api_key:
            # Configurar base URL para Singapore/Global region
            dashscope.base_http_api_url = 'https://dashscope-intl.aliyuncs.com/api/v1'
            logger.info("DashScope API configurada com sucesso")
        else:
            logger.warning("DASHSCOPE_API_KEY não encontrada")
        
        # Diretórios de saída
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)

    def _load_quota_state(self):
        try:
            if self._quota_file.exists():
                data = json.loads(self._quota_file.read_text(encoding="utf-8"))
                file_date = data.get("date")
                count = int(data.get("count", 0))
                today = datetime.now().date().isoformat()
                if file_date == today:
                    self._quota_date = file_date
                    self._quota_count = count
                else:
                    # reset for new day
                    self._quota_date = today
                    self._quota_count = 0
                    self._save_quota_state()
            else:
                self._save_quota_state()
        except Exception as e:
            logger.warning(f"Falha ao carregar estado de cota: {e}")

    def _save_quota_state(self):
        try:
            data = {"date": self._quota_date, "count": self._quota_count}
            self._quota_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Falha ao salvar estado de cota: {e}")

    async def _reserve_quota(self, units: int = 1):
        """Reserva cota antes de submeter tarefas ao provedor.
        Reseta diariamente.
        Lança QuotaExceededError se exceder a cota configurada.
        """
        async with self._quota_lock:
            today = datetime.now().date().isoformat()
            if self._quota_date != today:
                self._quota_date = today
                self._quota_count = 0
            if self._quota_count + units > self.free_quota:
                raise QuotaExceededError(
                    f"Limite de {self.free_quota} imagens/dia atingido. Tente novamente amanhã ou aumente a cota."
                )
            self._quota_count += units
            self._save_quota_state()

    async def _wait_for_rps_slot(self):
        """Garante no máximo self.rps_limit submissões por segundo."""
        while True:
            async with self._rps_lock:
                now = time.monotonic()
                # purge entries older than 1s
                while self._submission_window and (now - self._submission_window[0]) >= 1.0:
                    self._submission_window.popleft()
                if len(self._submission_window) < self.rps_limit:
                    self._submission_window.append(now)
                    return
                # tempo até liberar um slot
                sleep_time = 1.0 - (now - self._submission_window[0])
            await asyncio.sleep(max(0.0, sleep_time))

    def quota_status(self) -> Dict[str, Any]:
        """Retorna status atual da cota diária."""
        try:
            today = datetime.now().date().isoformat()
            # se mudou o dia e ainda não houve operação, refletir no retorno
            used = self._quota_count if self._quota_date == today else 0
            remaining = max(0, self.free_quota - used)
            return {
                "date": today,
                "limit": self.free_quota,
                "used": used,
                "remaining": remaining,
                "rps_limit": self.rps_limit,
                "max_concurrent": self.max_concurrent,
            }
        except Exception:
            return {"date": datetime.now().date().isoformat(), "limit": self.free_quota, "used": 0, "remaining": self.free_quota}

    def preprocess_technical_image(self, image_path, enable_crop=True):
        """
        Preprocessa imagem técnica:
        1. Adiciona quadrado branco nas coordenadas específicas
        2. Remove cabeçalho (150px) e rodapé (28px) se enable_crop=True
        """
        try:
            img = Image.open(image_path)
            img = img.convert('RGB')
            
            # Coordenadas do retângulo branco
            white_square_x = 1509
            white_square_y = 656
            white_square_w = 24
            white_square_h = 291
            
            # Desenhar quadrado branco
            draw = ImageDraw.Draw(img)
            x1 = white_square_x
            y1 = white_square_y
            x2 = white_square_x + white_square_w
            y2 = white_square_y + white_square_h
            draw.rectangle([x1, y1, x2, y2], fill='white')
            
            # Crop cabeçalho e rodapé somente se habilitado e com tamanho exato 1555x1000
            if enable_crop:
                width, height = img.size
                if (width, height) == (1555, 1000):
                    crop_top = 150
                    crop_bottom = 28
                    img = img.crop((0, crop_top, width, height - crop_bottom))
                    logger.info("Applied crop: technical image 1555x1000")
                else:
                    logger.info(
                        f"Skip crop: technical image size {width}x{height} != 1555x1000"
                    )
            
            return img
            
        except Exception as e:
            logger.error(f"Erro ao preprocessar imagem técnica: {e}")
            return None

    def preprocess_normal_image(self, image_path):
        """
        Preprocessa imagem normal:
        Adiciona quadrado branco central nas coordenadas específicas
        """
        try:
            img = Image.open(image_path)
            img = img.convert('RGB')
            
            # Coordenadas do retângulo branco central
            x1 = 1254
            y1 = 1390
            x2 = x1 + 183
            y2 = y1 + 45
            
            # Desenhar quadrado branco
            draw = ImageDraw.Draw(img)
            draw.rectangle([x1, y1, x2, y2], fill='white')
            
            return img
            
        except Exception as e:
            logger.error(f"Erro ao preprocessar imagem normal: {e}")
            return None

    def encode_image_to_data_uri(self, image):
        """Converte imagem para data URI"""
        try:
            if isinstance(image, (str, Path)):
                # Se for caminho de arquivo
                mime_type = mimetypes.guess_type(str(image))[0]
                if not mime_type or not mime_type.startswith("image/"):
                    return None
                with open(image, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                return f"data:{mime_type};base64,{b64}"
            else:
                # Se for objeto PIL Image
                buffer = io.BytesIO()
                image.save(buffer, format='PNG')
                buffer.seek(0)
                b64 = base64.b64encode(buffer.read()).decode("utf-8")
                return f"data:image/png;base64,{b64}"
        except Exception as e:
            logger.error(f"Erro ao codificar imagem: {e}")
            return None

    def encode_image_file_to_base64(self, image_path: str) -> Optional[str]:
        """Lê um arquivo de imagem e retorna base64 (sem prefixo data URI)"""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Erro ao converter arquivo para base64: {e}")
            return None

    def download_image_to_tempfile(self, url: str) -> Optional[str]:
        """Baixa uma imagem para um arquivo temporário e retorna o caminho."""
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                logger.error(f"URL não é imagem: {content_type}")
                return None
            suffix = mimetypes.guess_extension(content_type) or ".jpg"
            fd, temp_path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(r.content)
            return temp_path
        except Exception as e:
            logger.error(f"Erro ao baixar imagem da URL: {e}")
            return None

    async def generate_from_qwen(self, image, prompt, original_filename):
        """
        Gera imagem editada usando DashScope Qwen
        
        Args:
            image: Imagem PIL ou caminho
            prompt: Prompt para o AI
            original_filename: Nome do arquivo original
            
        Returns:
            Dict com resultado ou None
        """
        if not self.api_key:
            logger.error("DASHSCOPE_API_KEY não configurada")
            return None
        
        # Respeitar RPS e concorrência
        await self._wait_for_rps_slot()
        async with self._concurrency_semaphore:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._generate_sync, image, prompt, original_filename)
    
    def _generate_sync(self, image, prompt, original_filename):
        """Versão síncrona da geração"""
        try:
            data_uri = self.encode_image_to_data_uri(image)
            if not data_uri:
                logger.error("Falha ao codificar imagem")
                return None
            
            messages = [{
                "role": "user",
                "content": [
                    {"image": data_uri},
                    {"text": prompt}
                ]
            }]

            # Chamar DashScope
            response = MultiModalConversation.call(
                api_key=self.api_key,
                model="qwen-image-edit",
                messages=messages,
                result_format='message',
                stream=False,
                watermark=False,
                negative_prompt="logos, watermark, text overlays, header, footer"
            )

            # Verificar resposta
            if getattr(response, "status_code", None) == 200 and "output" in response:
                choices = response["output"].get("choices", [])
                if choices and "message" in choices[0]:
                    contents = choices[0]["message"].get("content", [])
                    for part in contents:
                        if isinstance(part, dict) and "image" in part:
                            # Baixar resultado (em memória e opcionalmente salvar)
                            return self._download_qwen_result(part["image"], original_filename)
            
            logger.error("Resposta inválida do Qwen")
            return None
            
        except Exception as e:
            logger.error(f"Erro na chamada Qwen: {e}")
            return None

    def _download_qwen_result(self, url: str, original_filename: str) -> Optional[Dict[str, Any]]:
        """Baixa a imagem resultante do Qwen. Salva em disco somente se habilitado."""
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()

            content = r.content
            unique_id = uuid.uuid4().hex[:6]
            filename_base = Path(original_filename).stem
            suggested_name = f"{filename_base}_processed_{unique_id}.png"

            if self.save_files:
                output_path = self.output_dir / suggested_name
                with open(output_path, "wb") as f:
                    f.write(content)
                return {
                    "filename": output_path.name,
                    "path": str(output_path),
                    "size": len(content)
                }
            else:
                return {
                    "filename": suggested_name,
                    "bytes": content,
                    "size": len(content)
                }
        except Exception as e:
            logger.error(f"Erro ao baixar imagem: {e}")
            return None

    def trim_white_borders(self, im, threshold=240):
        """Remove bordas brancas da imagem"""
        gray_im = im.convert('L')
        bin_im = gray_im.point(lambda p: 255 if p > threshold else p)
        inverted_im = ImageChops.invert(bin_im)
        bbox = inverted_im.getbbox()
        return im.crop(bbox) if bbox else im

    def add_corner_dots(self, image):
        """Adiciona pontos pretos nos 4 cantos da imagem"""
        try:
            draw = ImageDraw.Draw(image)
            dot_radius = 3
            width, height = image.size
            offset = 2
            corners = [
                (offset, offset),
                (width - offset - dot_radius*2, offset),
                (offset, height - offset - dot_radius*2),
                (width - offset - dot_radius*2, height - offset - dot_radius*2)
            ]
            for x, y in corners:
                draw.ellipse([x, y, x + dot_radius*2, y + dot_radius*2], fill='black')
            
            return image
        except Exception as e:
            logger.error(f"Erro ao adicionar pontos: {e}")
            return image

    def format_image(self, image, apply_rotation, final_size=(1200, 1200)):
        """Formata imagem para tamanho padrão"""
        try:
            # Converter para RGB se necessário
            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA' or image.mode == 'LA':
                    background.paste(image, mask=image.split()[-1])
                else:
                    background.paste(image)
                image = background

            image = self.trim_white_borders(image, threshold=240)
            img_width, img_height = image.size

            if apply_rotation:
                aspect_ratio = img_width / img_height
                if aspect_ratio > 2:
                    image = image.rotate(-45, expand=True, fillcolor='white')
                    image = self.trim_white_borders(image, threshold=240)
                elif aspect_ratio < 0.5:
                    image = image.rotate(45, expand=True, fillcolor='white')
                    image = self.trim_white_borders(image, threshold=240)
            
            # Tornar quadrada
            img_width, img_height = image.size
            new_dim = max(img_width, img_height)
            new_img = Image.new("RGB", (new_dim, new_dim), "white")
            offset = ((new_dim - img_width) // 2, (new_dim - img_height) // 2)
            new_img.paste(image, offset)

            # Redimensionar
            new_img = new_img.resize(final_size, Image.LANCZOS)
            
            return new_img

        except Exception as e:
            logger.error(f"Erro ao formatar imagem: {e}")
            return None

    async def process_image(self, image_path, image_type="auto", enable_crop=True, 
                          apply_corner_dots=True, apply_rotation=True, original_name: Optional[str] = None):
        """
        Processa uma imagem completa
        
        Args:
            image_path: Caminho da imagem
            image_type: 'technical', 'normal' ou 'auto'
            enable_crop: Cortar cabeçalho/rodapé (técnicas)
            apply_corner_dots: Adicionar pontos (técnicas)
            apply_rotation: Aplicar rotação (normais)
            
        Returns:
            Dict com resultado do processamento
        """
        try:
            # Verificar e reservar cota (contabiliza submissões ao provedor)
            await self._reserve_quota(1)
            
            # Detectar tipo se auto
            if image_type == "auto":
                filename = Path(image_path).name
                image_type = "technical" if "_tec" in filename else "normal"
            
            logger.info(f"Processando imagem como tipo: {image_type}")
            
            # Preprocessar
            if image_type == "technical":
                preprocessed = self.preprocess_technical_image(image_path, enable_crop)
                prompt = self._get_technical_prompt()
            else:
                preprocessed = self.preprocess_normal_image(image_path)
                prompt = self._get_normal_prompt()
            
            if preprocessed is None:
                logger.error("Falha no preprocessamento")
                return None
            
            # Processar com Qwen (usar nome original, se informado, para nomear saída)
            original_for_naming = (original_name or Path(image_path).name)
            result = await self.generate_from_qwen(
                preprocessed, 
                prompt, 
                original_for_naming
            )
            
            if not result:
                logger.error("Falha no processamento Qwen")
                return None
            
            # Post-processar
            if "path" in result:
                processed_img = Image.open(result["path"])  # arquivo salvo
            else:
                processed_img = Image.open(io.BytesIO(result.get("bytes", b"")))  # em memória
            
            if image_type == "technical":
                # Formatar sem rotação
                formatted = self.format_image(processed_img, apply_rotation=False)
                if apply_corner_dots:
                    formatted = self.add_corner_dots(formatted)
            else:
                # Formatar com rotação
                formatted = self.format_image(processed_img, apply_rotation=apply_rotation)
            
            if self.save_files:
                # Salvar imagem final (garantir extensão .jpg)
                filename_stem = Path(result['filename']).stem
                final_path = self.output_dir / f"{filename_stem}_formatted.jpg"
                formatted.save(final_path, 'JPEG', quality=95)

                # Limpar arquivo intermediário se existe
                try:
                    if "path" in result and Path(result["path"]).exists():
                        os.remove(result["path"])
                except Exception:
                    pass

                return {
                    "filename": final_path.name,
                    "path": str(final_path),
                    "type": image_type,
                    "size": final_path.stat().st_size
                }
            else:
                # Não salvar: retornar base64 direto e um nome coerente
                b64 = self.encode_pil_to_base64(formatted)
                filename_stem = Path(result['filename']).stem if result.get('filename') else Path(original_for_naming).stem
                final_name = f"{filename_stem}_formatted.jpg"
                return {
                    "filename": final_name,
                    "path": None,
                    "type": image_type,
                    "size": len(b64) if b64 else 0,
                    "base64": b64
                }
            
        except QuotaExceededError:
            # Propagar para que o endpoint possa retornar 429
            raise
        except Exception as e:
            logger.error(f"Erro ao processar imagem: {e}")
            return None

    def _get_technical_prompt(self):
        """Retorna prompt para imagens técnicas"""
        return """ROLE: Ultra-conservative image cleaner.

TASK
- Remove the top header and all watermarks.
- Keep ONLY the product and any EXISTING technical overlays exactly as in the original.

STRICT RULES
- Never add or modify technical graphics or text. If the image has no overlays, DO NOT create any.
- Preserve pixel geometry, colors, textures, shadows of the product.
- Preserve overlays pixel-accurate: lines, arrows, numbers, units (mm, Ø), labels, boxes, fonts, thickness, alignment, and positions.
- If a watermark crosses an overlay, erase watermark pixels ONLY; do not soften, shift, or redraw the overlay.
- Background must be pure white (#FFFFFF). No gradients/props.
- Keep original canvas size/resolution; crop only to remove the header.
- Output PNG (lossless). If exact cleanup would alter overlays, return: UNSAFE_TO_EDIT.

PROCESS
- Build PROTECT MASK = product + all overlays. EDIT MASK = header + watermark + background.
- Inpaint ONLY inside EDIT MASK with minimal radius.

NEGATIVE PROMPT: Do not: add/create/generate text, numbers, dimensions, units, arrows, lines, callouts, labels, logos, badges, extra parts, reflections, highlights, borders, gradients, textures, background patterns; do not translate text; do not change fonts, thickness, kerning, colors, alignment, or positions; do not smooth/antialias edges of overlays; do not rescale/reshape/repaint the product; no hallucination or synthesis of missing pixels."""

    def _get_normal_prompt(self):
        """Retorna prompt para imagens normais"""
        return """ROLE: Ultra-conservative image cleaner.

TASK
- Remove all watermarks.
- Keep ONLY the product as in the original.

STRICT RULES
- Preserve pixel geometry, colors, textures, shadows of the product.
- Background must be pure white (#FFFFFF). No gradients/props.
- Keep original canvas size/resolution.
- Output PNG (lossless). If exact cleanup would alter overlays, return: UNSAFE_TO_EDIT.

PROCESS
- Build PROTECT MASK = product + all overlays. EDIT MASK = header + watermark + background.
- Inpaint ONLY inside EDIT MASK with minimal radius.

NEGATIVE PROMPT: Do not: add/create/generate text, numbers, dimensions, units, arrows, lines, callouts, labels, logos, badges, extra parts, reflections, highlights, borders, gradients, textures, background patterns; do not translate text; do not change fonts, thickness, kerning, colors, alignment, or positions; do not smooth/antialias edges of overlays; do not rescale/reshape/repaint the product; no hallucination or synthesis of missing pixels."""

    def encode_pil_to_base64(self, image: Image.Image) -> Optional[str]:
        """Codifica uma PIL Image para base64 (sem prefixo data URI)."""
        try:
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=95)
            buffer.seek(0)
            return base64.b64encode(buffer.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Erro ao converter PIL para base64: {e}")
            return None