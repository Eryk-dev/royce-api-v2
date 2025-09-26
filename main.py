"""
API Royce - Sistema unificado para gerenciamento de produtos Royce
Autor: 141AIR
Data: 2025
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging
import os
from pathlib import Path
from datetime import datetime
import json
import uvicorn
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

# Importar serviços
from services.scraping_service import ScrapingService
from services.product_service import ProductService
from services.json_processor_service import JSONProcessorService
from services.image_processor_service import ImageProcessorService

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Criar instância da API
# Criar instância da API
app = FastAPI(
    title="Royce API",
    description="API para gerenciamento de produtos Royce - Scraping, Processamento de JSON e Imagens",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instanciar serviços
scraping_service = ScrapingService()
product_service = ProductService()
json_processor_service = JSONProcessorService()
image_processor_service = ImageProcessorService()

# ========================= MODELOS =========================

class ProductSearchResponse(BaseModel):
    timestamp: str
    total_esperado: int
    total_coletado: int
    paginas_processadas: int
    tempo_execucao: float
    codigos: List[str]
    problemas: Optional[Dict[str, Any]] = None

class ProductDetailResponse(BaseModel):
    timestamp: str
    codigo_pesquisado: str
    encontrado: bool
    dados: Optional[Dict[str, Any]] = None
    url_pesquisa: str
    erro: Optional[str] = None

class JSONProcessRequest(BaseModel):
    source_data: Dict[str, Any] = Field(..., description="Dados JSON no formato da pasta 'teste apis royce'")
    codigo_produto: Optional[str] = Field(None, description="Código do produto (opcional)")

class JSONProcessResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class ImageProcessRequest(BaseModel):
    image_type: str = Field(..., description="Tipo de imagem: 'technical' ou 'normal'")
    enable_crop: bool = Field(True, description="Cortar cabeçalho/rodapé em imagens técnicas")
    apply_corner_dots: bool = Field(True, description="Adicionar pontos nos cantos (apenas técnicas)")
    apply_rotation: bool = Field(True, description="Aplicar rotação automática (apenas normais)")

class ImageProcessResponse(BaseModel):
    success: bool
    message: str
    original_filename: str
    processed_filename: Optional[str] = None
    processing_time: Optional[float] = None
    error: Optional[str] = None

class ImageUrlProcessRequest(BaseModel):
    url: str = Field(..., description="URL pública da imagem")
    image_type: str = Field("auto", description="technical|normal|auto (auto detecta por sufixo _tec no filename)")
    enable_crop: bool = True
    apply_corner_dots: bool = True
    apply_rotation: bool = True

class ImageUrlProcessResponse(BaseModel):
    success: bool
    message: str
    source_url: str
    processed_filename: Optional[str] = None
    processing_time: Optional[float] = None
    base64: Optional[str] = None
    error: Optional[str] = None

class ImageUrlsBatchRequest(BaseModel):
    urls: List[str] = Field(..., description="Lista de URLs de imagens")
    enable_crop: bool = True
    apply_corner_dots: bool = True
    apply_rotation: bool = True

class ImageUrlsBatchResponse(BaseModel):
    results: List[ImageUrlProcessResponse]

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    services: Dict[str, str]
    version: str

# ========================= ENDPOINTS =========================

@app.get("/", response_model=Dict[str, str])
async def root():
    """Endpoint raiz com informações básicas da API"""
    return {
        "name": "Royce API",
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/health"
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Verificar saúde da API e serviços"""
    services_status = {
        "scraping": "operational",
        "product_search": "operational",
        "json_processor": "operational",
        "image_processor": "operational"
    }
    
    # Verificar se as chaves de API estão configuradas e serviços inicializados
    if not os.getenv("GEMINI_API_KEY"):
        services_status["json_processor"] = "degraded - missing GEMINI_API_KEY"
    elif not json_processor_service.model:
        services_status["json_processor"] = "degraded - model not initialized"
    
    if not os.getenv("DASHSCOPE_API_KEY"):
        services_status["image_processor"] = "degraded - missing DASHSCOPE_API_KEY"
    elif not image_processor_service.api_key:
        services_status["image_processor"] = "degraded - API key not loaded"
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        services=services_status,
        version="1.0.0"
    )

@app.get("/produtos", response_model=ProductSearchResponse)
async def get_all_products(
    max_pages: int = 30,
    items_per_page: int = 200
):
    """
    Realizar scraping completo de todos os produtos Royce
    
    - **max_pages**: Número máximo de páginas a processar (padrão: 30)
    - **items_per_page**: Itens por página (padrão: 200)
    """
    try:
        logger.info(f"Iniciando scraping completo - max_pages: {max_pages}, items_per_page: {items_per_page}")
        
        resultado = await scraping_service.scraping_pesquisa_completa(
            max_pages=max_pages,
            items_per_page=items_per_page
        )
        
        if resultado:
            return ProductSearchResponse(**resultado)
        else:
            raise HTTPException(status_code=500, detail="Erro ao realizar scraping")
            
    except Exception as e:
        logger.error(f"Erro no endpoint /produtos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/produto/{codigo_produto}", response_model=ProductDetailResponse)
async def get_product_details(codigo_produto: str):
    """
    Buscar informações detalhadas de um produto específico
    
    - **codigo_produto**: Código do produto (ex: RC.600.021)
    """
    try:
        logger.info(f"Buscando produto: {codigo_produto}")
        
        resultado = await product_service.buscar_produto_royce(codigo_produto)
        
        if resultado:
            return ProductDetailResponse(**resultado)
        else:
            raise HTTPException(status_code=404, detail=f"Produto {codigo_produto} não encontrado")
            
    except Exception as e:
        logger.error(f"Erro ao buscar produto {codigo_produto}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/produtos/json", response_model=JSONProcessResponse)
async def process_json(request: JSONProcessRequest):
    """
    Processar JSON de produto usando Gemini AI
    
    Transforma dados do formato 'teste apis royce' para o formato 'Json Royce'
    """
    try:
        logger.info(f"Processando JSON para produto: {request.codigo_produto or 'unknown'}")
        
        # Verificar se API key está configurada
        if not os.getenv("GEMINI_API_KEY"):
            raise HTTPException(
                status_code=503, 
                detail="Serviço indisponível - GEMINI_API_KEY não configurada"
            )
        
        resultado = await json_processor_service.transform_with_gemini(request.source_data)
        
        if resultado:
            return JSONProcessResponse(
                success=True,
                message="JSON processado com sucesso",
                data=resultado,
                error=None
            )
        else:
            return JSONProcessResponse(
                success=False,
                message="Falha ao processar JSON",
                data=None,
                error="Não foi possível transformar os dados"
            )
            
    except Exception as e:
        logger.error(f"Erro ao processar JSON: {str(e)}")
        return JSONProcessResponse(
            success=False,
            message="Erro ao processar JSON",
            data=None,
            error=str(e)
        )

@app.post("/pictures", response_model=ImageProcessResponse)
async def process_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    image_type: str = "auto",
    enable_crop: bool = True,
    apply_corner_dots: bool = True,
    apply_rotation: bool = True
):
    """
    Processar imagem de produto usando Qwen AI
    
    - **file**: Arquivo de imagem (JPG, PNG, WEBP)
    - **image_type**: 'technical', 'normal' ou 'auto' (detecta automaticamente)
    - **enable_crop**: Cortar cabeçalho/rodapé em imagens técnicas
    - **apply_corner_dots**: Adicionar pontos nos cantos (apenas técnicas)
    - **apply_rotation**: Aplicar rotação automática (apenas normais)
    """
    try:
        # Verificar se API key está configurada
        if not os.getenv("DASHSCOPE_API_KEY"):
            raise HTTPException(
                status_code=503,
                detail="Serviço indisponível - DASHSCOPE_API_KEY não configurada"
            )
        
        # Validar tipo de arquivo
        allowed_types = ["image/jpeg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de arquivo não suportado: {file.content_type}"
            )
        
        logger.info(f"Processando imagem: {file.filename}, tipo: {image_type}")
        
        # Salvar arquivo temporariamente
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        
        temp_path = temp_dir / file.filename
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Detectar tipo se auto
        if image_type == "auto":
            image_type = "technical" if "_tec" in file.filename else "normal"
        
        # Processar imagem
        start_time = datetime.now()
        
        try:
            resultado = await image_processor_service.process_image(
                image_path=str(temp_path),
                image_type=image_type,
                enable_crop=enable_crop,
                apply_corner_dots=apply_corner_dots,
                apply_rotation=apply_rotation
            )
        except Exception as ex:
            # Mapear erro de cota do provedor para 429
            if ex.__class__.__name__ == 'QuotaExceededError':
                qs = image_processor_service.quota_status()
                raise HTTPException(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    detail={"message": "Cota diária de imagens atingida", "quota": qs}
                )
            raise
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Limpar arquivo temporário em background
        background_tasks.add_task(os.remove, temp_path)
        
        if resultado:
            return ImageProcessResponse(
                success=True,
                message=f"Imagem processada com sucesso como tipo '{image_type}'",
                original_filename=file.filename,
                processed_filename=resultado.get("filename"),
                processing_time=processing_time,
                error=None
            )
        else:
            return ImageProcessResponse(
                success=False,
                message="Falha ao processar imagem",
                original_filename=file.filename,
                processed_filename=None,
                processing_time=processing_time,
                error="Processamento falhou"
            )
            
    except Exception as e:
        logger.error(f"Erro ao processar imagem: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/pictures/url", response_model=ImageUrlProcessResponse)
async def process_image_from_url(
    request: ImageUrlProcessRequest
):
    """
    Processa imagem a partir de uma URL e retorna também o base64 do arquivo final.
    """
    try:
        if not os.getenv("DASHSCOPE_API_KEY"):
            raise HTTPException(status_code=503, detail="Serviço indisponível - DASHSCOPE_API_KEY não configurada")

        logger.info(f"Baixando imagem da URL: {request.url}")

        # Auto-detectar tipo pelo nome da URL se image_type=auto
        detected_type = request.image_type
        if request.image_type == "auto":
            filename_lower = request.url.lower()
            detected_type = "technical" if "_tec" in filename_lower else "normal"

        # Baixar imagem para arquivo temporário
        temp_path = image_processor_service.download_image_to_tempfile(request.url)
        if not temp_path:
            raise HTTPException(status_code=400, detail="Falha ao baixar a imagem da URL")

        start_time = datetime.now()
        try:
            result = await image_processor_service.process_image(
            image_path=temp_path,
            image_type=detected_type,
            enable_crop=request.enable_crop,
            apply_corner_dots=request.apply_corner_dots,
            apply_rotation=request.apply_rotation,
            original_name=request.url.split('/')[-1]
        )
        except Exception as ex:
            # Mapear erro de cota
            if ex.__class__.__name__ == 'QuotaExceededError':
                qs = image_processor_service.quota_status()
                raise HTTPException(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    detail={"message": "Cota diária de imagens atingida", "quota": qs}
                )
            raise

        # Remover arquivo temporário
        try:
            os.remove(temp_path)
        except Exception:
            pass

        processing_time = (datetime.now() - start_time).total_seconds()

        if not result:
            return ImageUrlProcessResponse(
                success=False,
                message="Falha ao processar imagem",
                source_url=request.url,
                processing_time=processing_time,
                error="Processamento falhou"
            )

        # Ajustar resposta conforme modo de salvamento:
        # - Se houver caminho (arquivos salvos), ler e devolver base64 do arquivo final
        # - Caso contrário, usar base64 retornado pelo serviço (modo consulta)
        final_base64 = ""
        if result.get("path"):
            final_base64 = image_processor_service.encode_image_file_to_base64(result["path"]) or ""
        else:
            final_base64 = result.get("base64") or ""

        return ImageUrlProcessResponse(
            success=True,
            message=f"Imagem processada com sucesso como tipo '{result['type']}'",
            source_url=request.url,
            processed_filename=result.get("filename"),
            processing_time=processing_time,
            base64=final_base64,
            error=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao processar imagem por URL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/pictures/urls", response_model=ImageUrlsBatchResponse)
async def process_images_batch(
    request: ImageUrlsBatchRequest
):
    """
    Processa múltiplas imagens em paralelo.
    - Detecta automaticamente 'technical' quando a URL contém '_tec'.
    - Retorna base64 de cada imagem final no campo base64.
    """
    try:
        if not os.getenv("DASHSCOPE_API_KEY"):
            raise HTTPException(status_code=503, detail="Serviço indisponível - DASHSCOPE_API_KEY não configurada")

        # Pré-checagem de cota: se não houver cota suficiente para o lote, retornar 429
        try:
            qs = image_processor_service.quota_status()
            remaining = int(qs.get("remaining", 0))
        except Exception:
            remaining = 0
        if len(request.urls) > 0 and remaining <= 0:
            raise HTTPException(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                detail={"message": "Cota diária de imagens atingida", "quota": image_processor_service.quota_status()}
            )

        async def _process_one(url: str) -> ImageUrlProcessResponse:
            try:
                filename_lower = url.lower()
                detected_type = "technical" if "_tec" in filename_lower else "normal"

                temp_path = image_processor_service.download_image_to_tempfile(url)
                if not temp_path:
                    return ImageUrlProcessResponse(
                        success=False,
                        message="Falha ao baixar a imagem",
                        source_url=url,
                        processed_filename=None,
                        processing_time=None,
                        base64=None,
                        error="Download falhou"
                    )

                start_time = datetime.now()
                try:
                    result = await image_processor_service.process_image(
                    image_path=temp_path,
                    image_type=detected_type,
                    enable_crop=request.enable_crop,
                    apply_corner_dots=request.apply_corner_dots,
                    apply_rotation=request.apply_rotation,
                    original_name=url.split('/')[-1]
                )
                except Exception as ex:
                    if ex.__class__.__name__ == 'QuotaExceededError':
                        qs = image_processor_service.quota_status()
                        return ImageUrlProcessResponse(
                            success=False,
                            message="Cota diária de imagens atingida",
                            source_url=url,
                            processed_filename=None,
                            processing_time=None,
                            base64=None,
                            error=json.dumps(qs)
                        )
                    raise

                try:
                    os.remove(temp_path)
                except Exception:
                    pass

                processing_time = (datetime.now() - start_time).total_seconds()

                if not result:
                    return ImageUrlProcessResponse(
                        success=False,
                        message="Falha ao processar imagem",
                        source_url=url,
                        processed_filename=None,
                        processing_time=processing_time,
                        base64=None,
                        error="Processamento falhou"
                    )

                if result.get("path"):
                    final_base64 = image_processor_service.encode_image_file_to_base64(result["path"]) or ""
                else:
                    final_base64 = result.get("base64") or ""

                return ImageUrlProcessResponse(
                    success=True,
                    message=f"Imagem processada com sucesso como tipo '{result['type']}'",
                    source_url=url,
                    processed_filename=result.get("filename"),
                    processing_time=processing_time,
                    base64=final_base64,
                    error=None
                )
            except Exception as ex:
                logger.error(f"Erro no item {url}: {ex}")
                return ImageUrlProcessResponse(
                    success=False,
                    message="Erro ao processar imagem",
                    source_url=url,
                    processed_filename=None,
                    processing_time=None,
                    base64=None,
                    error=str(ex)
                )

        # Executar em paralelo
        import asyncio as _asyncio
        tasks = [_asyncio.create_task(_process_one(u)) for u in request.urls]
        results = await _asyncio.gather(*tasks)
        return ImageUrlsBatchResponse(results=results)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no processamento em lote de imagens: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/pictures/quota", response_model=Dict[str, Any])
async def get_pictures_quota():
    """Retorna o status atual de cota/limites do editor de imagens."""
    try:
        return image_processor_service.quota_status()
    except Exception as e:
        logger.error(f"Erro ao obter status de cota: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/produtos/batch", response_model=Dict[str, Any])
async def batch_scraping(
    codigos: List[str],
    background_tasks: BackgroundTasks
):
    """
    Buscar múltiplos produtos em lote
    
    - **codigos**: Lista de códigos de produtos
    """
    try:
        if len(codigos) > 100:
            raise HTTPException(
                status_code=400,
                detail="Máximo de 100 produtos por requisição"
            )
        
        logger.info(f"Processamento em lote iniciado para {len(codigos)} produtos")
        
        # Processar em background
        task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        background_tasks.add_task(
            product_service.batch_search,
            codigos,
            task_id
        )
        
        return {
            "message": "Processamento iniciado",
            "task_id": task_id,
            "total_products": len(codigos),
            "status_endpoint": f"/tasks/{task_id}"
        }
        
    except Exception as e:
        logger.error(f"Erro no processamento em lote: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Verificar status de uma tarefa em background"""
    # Implementar verificação de status
    return {
        "task_id": task_id,
        "status": "processing",
        "message": "Funcionalidade em desenvolvimento"
    }

# ========================= EXCEPTION HANDLERS =========================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint não encontrado", "path": str(request.url)}
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Erro interno do servidor", "detail": str(exc)}
    )

# ========================= STARTUP/SHUTDOWN =========================

@app.on_event("startup")
async def startup_event():
    """Inicialização da API"""
    logger.info("🚀 Royce API iniciando...")
    
    # Criar diretórios necessários
    dirs = ["temp_uploads", "output", "logs"]
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
    
    # Verificar variáveis de ambiente
    env_vars = ["GEMINI_API_KEY", "DASHSCOPE_API_KEY"]
    for var in env_vars:
        if os.getenv(var):
            logger.info(f"✅ {var} configurada")
        else:
            logger.warning(f"⚠️ {var} não encontrada")
    
    logger.info("✅ API pronta para receber requisições")

@app.on_event("shutdown")
async def shutdown_event():
    """Encerramento da API"""
    logger.info("🔚 Encerrando Royce API...")
    
    # Limpar arquivos temporários
    temp_dir = Path("temp_uploads")
    if temp_dir.exists():
        for file in temp_dir.glob("*"):
            try:
                file.unlink()
            except:
                pass
    
    logger.info("👋 API encerrada")

# ========================= MAIN =========================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5682,
        reload=False,
        log_level="info"
    )


