"""
Serviço de Processamento JSON com Gemini - Adaptado de processar_jsons_gemini.py
"""

import os
import json
import logging
from typing import Dict, Any, Optional
import google.generativeai as genai
from dotenv import load_dotenv
import asyncio

logger = logging.getLogger(__name__)

class JSONProcessorService:
    def __init__(self):
        """Inicializa o processador com a chave da API do Gemini"""
        load_dotenv()
        
        self.api_key = os.getenv('GEMINI_API_KEY')
        
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.5-pro')
            logger.info("Gemini API configurada com sucesso")
        else:
            logger.warning("GEMINI_API_KEY não encontrada")
            self.model = None

    def create_transformation_prompt(self, source_data: Dict[str, Any]) -> str:
        """
        Cria o prompt para o Gemini transformar os dados
        
        Args:
            source_data: Dados do JSON de origem
            
        Returns:
            Prompt formatado
        """
        product_info = source_data.get('dados', [{}])[0] if source_data.get('dados') else {}

        prompt = f"""
Você é um especialista em processamento de dados de produtos automotivos. Analise os dados fornecidos e extraia TODAS as informações estruturadas disponíveis, organizando-as no formato correto.

**DADOS DE ORIGEM DISPONÍVEIS:**
{json.dumps(product_info, indent=2, ensure_ascii=False)}

**INSTRUÇÕES PARA EXTRAÇÃO INTELIGENTE:**

1. **USE TODAS as informações disponíveis** nos campos: codigo, nome, imagens, descricao
2. **EXTRAI informações estruturadas** do texto do nome do produto
3. **PREENCHA os campos** quando houver dados suficientes
4. **DEIXE VAZIO** apenas quando realmente não houver informação

**COMPATIBILITY - EXTRAIA SE DISPONÍVEL:**
- Procure informações de veículos no campo "nome"
- Estrutura: marca, modelo, ano inicial/final, motor, combustível
- Se não houver informações de veículos, use: {{"vehicles": []}}

**SPECIFICATIONS - EXTRAIA TODAS AS INFORMAÇÕES TÉCNICAS:**
- Modelo, Voltagem, Polia, Tipo de correia, Diâmetro
- Tipo de montagem, Gás refrigerante, Óleo
- Vias, Tipo de conexão, Pressões, Qualidade
- Sempre inclua "Marca": "Royce"
- Se não houver especificações, use: {{}}

**ADDITIONAL_INFO - EXTRAIA INFORMAÇÕES COMPLEMENTARES:**
- Material, Dimensões, Peso
- Originalidade, Diâmetro, Pesos líquido/bruto
- Se não houver informações adicionais, use: {{}}

**FORMATO DE SAÍDA FINAL:**

```json
{{
  "data": {{
    "product_name": "Nome do produto",
    "código fornecedor": ["Código"],
    "código oem": ["Códigos OEM"],
    "url_imgs": ["URLs convertidas"],
    "compatibility": {{
      "vehicles": [
        {{
          "brand": "Marca",
          "model": "Modelo",
          "year_range": {{
            "start": "Ano inicial",
            "end": "Ano final"
          }},
          "engine": "Motor",
          "fuel": "Combustível"
        }}
      ]
    }},
    "specifications": {{
      "Marca": "Royce",
      "outras especificações extraídas": "valores"
    }},
    "additional_info": {{
      "informações complementares": "valores"
    }},
    "equivalente HDS": ""
  }},
  "sources": []
}}
```

**EXEMPLOS DE EXTRAÇÃO:**

ENTRADA: "Compressor Modelo AB7H15AB 4358 Caminhão DAF XF FTS 480 2021> - 24 Volts Polia 8pk 165mm OEM: 2046604"
SAÍDA:
- product_name: "Compressor Modelo AB7H15AB 4358 Caminhão DAF XF FTS 480 2021> - 24 Volts Polia 8pk 165mm"
- código oem: ["2046604"]
- compatibility: {{"vehicles": [{{"brand": "DAF", "model": "XF FTS 480", "year_range": {{"start": "2021", "end": ""}}}}]}}
- specifications: {{"Modelo": "AB7H15AB 4358", "Voltagem": "24 Volts", "Polia": "8pk 165mm", "Marca": "Royce"}}

**IMPORTANTE:**
- Extraia TODAS as informações estruturadas disponíveis no texto
- Use o formato correto para cada campo
- Se uma informação não estiver disponível, deixe o campo vazio
- Seja preciso e não invente informações
"""

        return prompt

    async def transform_with_gemini(self, source_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Transforma os dados usando o Gemini
        
        Args:
            source_data: Dados do JSON de origem
            
        Returns:
            Dados transformados ou None se falhar
        """
        if not self.model:
            logger.error("Modelo Gemini não configurado")
            return None
        
        # Executar em thread separada
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transform_sync, source_data)
    
    def _transform_sync(self, source_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Versão síncrona da transformação"""
        try:
            if not source_data.get('dados'):
                logger.warning("Dados vazios encontrados")
                
                # Retornar estrutura padrão para dados vazios
                return {
                    "data": {
                        "product_name": "",
                        "código fornecedor": [],
                        "código oem": [],
                        "url_imgs": [],
                        "compatibility": {"vehicles": []},
                        "specifications": {"Marca": "Royce"},
                        "additional_info": {},
                        "equivalente HDS": ""
                    },
                    "sources": []
                }

            prompt = self.create_transformation_prompt(source_data)

            response = self.model.generate_content(prompt)

            if not response.text:
                logger.error("Resposta vazia do Gemini")
                return None

            # Limpar a resposta para obter apenas o JSON
            json_text = response.text.strip()

            # Remover markdown code blocks se presentes
            if json_text.startswith('```json'):
                json_text = json_text[7:]
            if json_text.endswith('```'):
                json_text = json_text[:-3]

            json_text = json_text.strip()

            # Fazer parse do JSON
            transformed_data = json.loads(json_text)

            # Validação básica
            if 'data' not in transformed_data:
                logger.error("JSON transformado não contém chave 'data'")
                return None

            # Adicionar código do produto se disponível
            if source_data.get('dados') and source_data['dados'][0].get('codigo'):
                codigo = source_data['dados'][0]['codigo']
                logger.info(f"Dados transformados com sucesso para {codigo}")

            return transformed_data

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao fazer parse do JSON: {e}")
            if 'response' in locals():
                logger.debug(f"Texto recebido: {response.text}")
            return None
        except Exception as e:
            logger.error(f"Erro ao processar com Gemini: {e}")
            return None
        
    async def process_batch(self, source_data_list: list) -> list:
        """
        Processa múltiplos JSONs em lote
        
        Args:
            source_data_list: Lista de dados JSON
            
        Returns:
            Lista de resultados transformados
        """
        results = []
        
        for source_data in source_data_list:
            result = await self.transform_with_gemini(source_data)
            results.append(result)
            
            # Pequena pausa para não exceder rate limits
            await asyncio.sleep(0.5)
        
        return results



