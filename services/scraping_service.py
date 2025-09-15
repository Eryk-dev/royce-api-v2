"""
Serviço de Scraping - Adaptado de scraping_royce_pesquisa_completa.py
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import json
import time
import re
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)

class ScrapingService:
    def __init__(self):
        self.base_url = "https://www.royce.com.br/pesquisa"
        
    def configurar_driver(self):
        """Configura o driver Chrome otimizado para máxima velocidade"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--disable-javascript')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-web-security')
        
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.plugins": 2,
            "profile.managed_default_content_settings.popups": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.page_load_strategy = 'eager'
        
        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception:
            driver = webdriver.Chrome(options=chrome_options)
        driver.implicitly_wait(3)
        return driver

    def extrair_codigos_pagina(self, driver):
        """Extrai códigos de produtos de uma página de pesquisa"""
        codigos = []
        produtos_sem_codigo = []
        links_invalidos = []
        
        try:
            wait = WebDriverWait(driver, 5)
            wait.until(EC.presence_of_element_located((By.ID, "div-lista-produtos")))
            
            links_produtos = driver.find_elements(By.XPATH, "//a[contains(@href, '/item/')]")
            
            for i, link in enumerate(links_produtos):
                href = link.get_attribute('href')
                if href:
                    match = re.search(r'/item/([^/]+)/', href)
                    if match:
                        codigo = match.group(1)
                        if codigo not in codigos:
                            codigos.append(codigo)
                    else:
                        produtos_sem_codigo.append(href)
                else:
                    links_invalidos.append(f"Link {i+1} sem href")
            
            if produtos_sem_codigo:
                logger.warning(f"{len(produtos_sem_codigo)} links sem código válido")
            if links_invalidos:
                logger.warning(f"{len(links_invalidos)} links inválidos")
            
            return codigos, produtos_sem_codigo, links_invalidos
        
        except Exception as e:
            logger.error(f"Erro ao extrair códigos da página: {e}")
            return [], [], []

    def obter_total_produtos(self, driver):
        """Obtém o número total de produtos da página"""
        try:
            elemento_total = driver.find_element(By.XPATH, "//*[contains(text(), 'produtos encontrados')]")
            texto = elemento_total.text
            match = re.search(r'(\d+)', texto)
            if match:
                return int(match.group(1))
        except:
            pass
        return 0

    def navegar_para_pagina(self, driver, pagina, tamanho=200):
        """Navega diretamente para uma página específica usando URL"""
        try:
            url = f"{self.base_url}?t=&tamanho={tamanho}&pagina={pagina}"
            driver.get(url)
            time.sleep(1.5)
            return True
        except Exception as e:
            logger.error(f"Erro ao navegar para página {pagina}: {e}")
            return False

    async def scraping_pesquisa_completa(self, max_pages=30, items_per_page=200):
        """
        Executa scraping completo da pesquisa geral
        
        Args:
            max_pages: Número máximo de páginas a processar
            items_per_page: Itens por página
            
        Returns:
            Dict com resultados do scraping
        """
        logger.info(f"Iniciando scraping completo - max_pages: {max_pages}, items_per_page: {items_per_page}")
        
        # Executar em thread separada para não bloquear
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._scraping_sync, max_pages, items_per_page)
    
    def _scraping_sync(self, max_pages, items_per_page):
        """Versão síncrona do scraping"""
        driver = self.configurar_driver()
        todos_codigos = []
        todas_duplicatas = []
        todos_problemas = {
            "produtos_sem_codigo": [],
            "links_invalidos": [],
            "paginas_com_problemas": []
        }
        
        try:
            url = f"{self.base_url}?t=&tamanho={items_per_page}"
            logger.info(f"Acessando: {url}")
            driver.get(url)
            time.sleep(3)
            
            total_esperado = self.obter_total_produtos(driver)
            logger.info(f"Total de produtos no site: {total_esperado}")
            
            pagina_atual = 1
            start_time = time.time()
            
            max_paginas_calculado = (total_esperado + items_per_page - 1) // items_per_page
            max_paginas_efetivo = min(max_paginas_calculado, max_pages)
            
            logger.info(f"Páginas a processar: {max_paginas_efetivo}")
            
            while pagina_atual <= max_paginas_efetivo:
                logger.info(f"Processando página {pagina_atual}/{max_paginas_efetivo}...")
                
                if pagina_atual > 1:
                    if not self.navegar_para_pagina(driver, pagina_atual, items_per_page):
                        logger.error(f"Falha ao carregar página {pagina_atual}")
                        break
                
                resultado_pagina = self.extrair_codigos_pagina(driver)
                codigos_pagina, produtos_sem_codigo, links_invalidos = resultado_pagina
                
                if produtos_sem_codigo or links_invalidos:
                    todos_problemas["paginas_com_problemas"].append(pagina_atual)
                    todos_problemas["produtos_sem_codigo"].extend(produtos_sem_codigo)
                    todos_problemas["links_invalidos"].extend(links_invalidos)
                
                if not codigos_pagina:
                    logger.info("Página sem produtos - fim atingido")
                    break
                
                novos_codigos = 0
                duplicatas_pagina = 0
                for codigo in codigos_pagina:
                    if codigo not in todos_codigos:
                        todos_codigos.append(codigo)
                        novos_codigos += 1
                    else:
                        duplicatas_pagina += 1
                        todas_duplicatas.append(codigo)
                
                logger.info(f"Página {pagina_atual}: {len(codigos_pagina)} códigos, "
                          f"{novos_codigos} novos, Total: {len(todos_codigos)}")
                
                pagina_atual += 1
                
                if pagina_atual % 5 == 0:
                    porcentagem = (len(todos_codigos) / total_esperado * 100) if total_esperado > 0 else 0
                    logger.info(f"Progresso: {porcentagem:.1f}% ({len(todos_codigos)}/{total_esperado})")
            
            elapsed_time = time.time() - start_time
            
            logger.info(f"Scraping concluído! Total de códigos: {len(todos_codigos)}")
            
            total_duplicatas = len(todas_duplicatas)
            total_sem_codigo = len(todos_problemas["produtos_sem_codigo"])
            total_links_invalidos = len(todos_problemas["links_invalidos"])
            diferenca = total_esperado - len(todos_codigos)
            
            resultado = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "metodo": "pesquisa_completa",
                "url_base": self.base_url,
                "total_esperado": total_esperado,
                "total_coletado": len(todos_codigos),
                "paginas_processadas": pagina_atual - 1,
                "tempo_execucao": round(elapsed_time, 1),
                "problemas": {
                    "total_duplicatas": total_duplicatas,
                    "produtos_sem_codigo": total_sem_codigo,
                    "links_invalidos": total_links_invalidos,
                    "diferenca_nao_explicada": diferenca - total_duplicatas - total_sem_codigo - total_links_invalidos,
                    "paginas_com_problemas": list(set(todos_problemas["paginas_com_problemas"])),
                    "exemplos_duplicatas": list(set(todas_duplicatas[:50])),
                    "exemplos_sem_codigo": todos_problemas["produtos_sem_codigo"][:20],
                    "exemplos_links_invalidos": todos_problemas["links_invalidos"][:20]
                },
                "codigos": todos_codigos
            }
            
            return resultado
            
        except Exception as e:
            logger.error(f"Erro fatal no scraping: {e}")
            return None
        
        finally:
            driver.quit()
            logger.info("Driver encerrado")



