"""
Serviço de Busca de Produtos - Adaptado de buscar_produto_royce.py
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import time
from datetime import datetime
import asyncio
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ProductService:
    def __init__(self):
        self.base_url = "https://www.royce.com.br"
        
    def configurar_driver(self):
        """Configura o driver do Chrome para velocidade"""
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-images")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-extensions")
        
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.plugins": 2,
            "profile.managed_default_content_settings.popups": 2,
        }
        options.add_experimental_option("prefs", prefs)
        options.page_load_strategy = 'eager'
        
        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception:
            # Fallback para PATH padrão (ex.: em containers com chromium-driver instalado)
            driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(3)
        return driver

    async def buscar_produto_royce(self, codigo_produto: str) -> Optional[Dict[str, Any]]:
        """
        Busca informações detalhadas de um produto específico da Royce
        
        Args:
            codigo_produto: Código do produto
            
        Returns:
            Dict com informações do produto ou None
        """
        logger.info(f"Buscando produto: {codigo_produto}")
        
        # Executar em thread separada
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._buscar_produto_sync, codigo_produto)
    
    def _buscar_produto_sync(self, codigo_produto: str) -> Optional[Dict[str, Any]]:
        """Versão síncrona da busca de produto"""
        driver = self.configurar_driver()
        wait = WebDriverWait(driver, 5)
        
        resultado = {
            "timestamp": datetime.now().isoformat(),
            "codigo_pesquisado": codigo_produto,
            "encontrado": False,
            "dados": {},
            "url_pesquisa": "",
            "erro": None
        }
        
        try:
            url = f"{self.base_url}/pesquisa?t={codigo_produto}"
            resultado["url_pesquisa"] = url
            
            logger.info(f"Acessando URL: {url}")
            driver.get(url)
            time.sleep(2)
            
            # Tentar aceitar cookies
            self._aceitar_cookies(driver)
            
            # Tentar encontrar o produto
            produto_encontrado = False
            produto_dados = {}
            
            try:
                # Verificar se existe lista de produtos
                lista_produtos_xpath = '//*[@id="div-lista-produtos"]/ul/li[1]/div/div/a'
                
                try:
                    primeiro_item = wait.until(EC.presence_of_element_located((By.XPATH, lista_produtos_xpath)))
                    driver.execute_script("arguments[0].click();", primeiro_item)
                    time.sleep(1)
                    produto_encontrado = True
                    logger.info("Produto encontrado na lista")
                    
                except (NoSuchElementException, TimeoutException):
                    # Tentar acessar diretamente
                    try:
                        produto_nome = wait.until(EC.presence_of_element_located(
                            (By.XPATH, '//*[@id="produto-detalhe"]/div/div[2]/div[1]/div/h1')
                        )).text
                        produto_encontrado = True
                        logger.info("Produto encontrado diretamente")
                    except:
                        pass
                
                if produto_encontrado:
                    # Extrair dados do produto
                    produto_dados = self._extrair_dados_produto(driver, codigo_produto)
                    produto_dados["url_produto"] = driver.current_url
                    
                    resultado["encontrado"] = True
                    resultado["dados"] = produto_dados
                
            except Exception as e:
                resultado["erro"] = f"Erro ao processar produto: {str(e)}"
                logger.error(f"Erro: {e}")
            
            if not produto_encontrado:
                resultado["erro"] = "Produto não encontrado na pesquisa"
                logger.warning("Produto não encontrado")
                
        except Exception as e:
            resultado["erro"] = f"Erro geral: {str(e)}"
            logger.error(f"Erro geral: {e}")
        
        finally:
            driver.quit()
            logger.info("Driver encerrado")
        
        return resultado

    def _aceitar_cookies(self, driver):
        """Tenta aceitar cookies se aparecerem"""
        try:
            cookie_selectors = [
                "//*[contains(@class, 'banner_cookie')]//button",
                "//button[contains(text(), 'Aceitar')]",
                "//button[contains(@class, 'cookie')]"
            ]
            
            for selector in cookie_selectors:
                try:
                    cookie_element = driver.find_element(By.XPATH, selector)
                    driver.execute_script("arguments[0].click();", cookie_element)
                    break
                except:
                    continue
        except:
            pass

    def _extrair_dados_produto(self, driver, codigo_produto):
        """Extrai todos os dados do produto"""
        produto_dados = {"codigo": codigo_produto}
        
        # Nome do produto
        try:
            nome_element = driver.find_element(By.XPATH, '//*[@id="produto-detalhe"]/div/div[2]/div[1]/div/h1')
            produto_dados["nome"] = nome_element.text.strip()
            logger.info(f"Nome: {produto_dados['nome']}")
        except:
            produto_dados["nome"] = "Nome não encontrado"
        
        # Código confirmado
        try:
            codigo_elements = driver.find_elements(By.XPATH, '//*[@id="produto-detalhe"]//span[contains(text(), "Código")]')
            if codigo_elements:
                codigo_confirmado = codigo_elements[0].text.replace("Código: ", "").strip()
                produto_dados["codigo_confirmado"] = codigo_confirmado
                logger.info(f"Código confirmado: {codigo_confirmado}")
            else:
                produto_dados["codigo_confirmado"] = codigo_produto
        except:
            produto_dados["codigo_confirmado"] = codigo_produto
        
        # Descrição/aplicações
        try:
            descricao_element = driver.find_element(By.XPATH, '//*[@id="produto-detalhe"]/div/div[2]/div[2]')
            produto_dados["descricao"] = descricao_element.text.strip()
            logger.info(f"Descrição encontrada: {len(produto_dados['descricao'])} caracteres")
        except:
            produto_dados["descricao"] = "Descrição não encontrada"
        
        # URL da imagem técnica
        try:
            links_fancybox = driver.find_elements(By.XPATH, "//a[@data-fancybox='gallery']")
            
            url_imagem_tecnica = None
            urls_imagens = []
            
            for link in links_fancybox:
                href = link.get_attribute('href')
                if href:
                    urls_imagens.append(href)
                    if '_tec' in href:
                        url_imagem_tecnica = href
            
            # Se não encontrou _tec, usar a última imagem
            if not url_imagem_tecnica and urls_imagens:
                url_imagem_tecnica = urls_imagens[-1]
            
            produto_dados["url_imagem_tecnica"] = url_imagem_tecnica
            produto_dados["urls_imagens"] = urls_imagens
            
            if url_imagem_tecnica:
                logger.info(f"Imagem técnica: {url_imagem_tecnica}")
        except:
            produto_dados["url_imagem_tecnica"] = None
            produto_dados["urls_imagens"] = []
        
        # Produtos relacionados
        try:
            wait = WebDriverWait(driver, 3)
            wait.until(EC.presence_of_element_located((By.ID, 'produtos-sugeridos')))
            
            script = '''
            var slides = document.querySelectorAll("#produtos-sugeridos .slick-slide");
            var products = [];
            slides.forEach(function(slide) {
                if (!slide.classList.contains("slick-cloned")) {
                    var codigoElement = slide.querySelector("font b");
                    var nomeElement = slide.querySelector("font");
                    if (codigoElement && nomeElement) {
                        var codigo = codigoElement.innerText.trim();
                        var nome = nomeElement.innerText.replace(codigo, "").trim();
                        products.push({'codigo': codigo, 'nome': nome});
                    }
                }
            });
            return products;
            '''
            
            relacionados = driver.execute_script(script)
            produto_dados["produtos_relacionados"] = relacionados
            logger.info(f"Produtos relacionados: {len(relacionados)} encontrados")
            
        except:
            produto_dados["produtos_relacionados"] = []
        
        return produto_dados
        
    async def batch_search(self, codigos: List[str], task_id: str):
        """
        Busca múltiplos produtos em lote
        
        Args:
            codigos: Lista de códigos de produtos
            task_id: ID da tarefa para tracking
        """
        logger.info(f"Iniciando busca em lote - Task ID: {task_id}, Total: {len(codigos)}")
        
        resultados = []
        for i, codigo in enumerate(codigos):
            logger.info(f"Processando {i+1}/{len(codigos)}: {codigo}")
            resultado = await self.buscar_produto_royce(codigo)
            resultados.append(resultado)
            
            # Pequena pausa entre requisições
            await asyncio.sleep(1)
        
        # Aqui você salvaria os resultados em algum lugar (banco de dados, arquivo, etc.)
        # Por enquanto, apenas logamos
        logger.info(f"Busca em lote concluída - Task ID: {task_id}")
        
        return resultados


