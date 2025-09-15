# Royce API - Sistema Unificado de Gerenciamento

API completa para gerenciamento de produtos Royce, incluindo scraping, processamento de JSON com IA e processamento de imagens.

## 🚀 Funcionalidades

- **Scraping Completo**: Coleta todos os produtos do site Royce
- **Busca de Produtos**: Informações detalhadas de produtos específicos
- **Processamento JSON**: Transformação inteligente com Gemini AI
- **Processamento de Imagens**: Limpeza e formatação com Qwen AI

## 📋 Pré-requisitos

- Python 3.11+
- Chrome/Chromium instalado
- API Keys:
  - Google Gemini API Key
  - DashScope (Alibaba Cloud) API Key

## 🔧 Instalação

### Método 1: Instalação Local

1. **Clone ou extraia o projeto**:
```bash
unzip royce-api.zip
cd royce-api
```

2. **Configure as variáveis de ambiente**:
```bash
cp .env.example .env
# Edite o arquivo .env com suas API keys
nano .env
```

3. **Instale as dependências**:
```bash
pip install -r requirements.txt
```

4. **Execute a API**:
```bash
python main.py
```

### Método 2: Docker

1. **Configure o .env**:
```bash
cp .env.example .env
nano .env
```

2. **Build e execute**:
```bash
docker-compose up -d --build
```

### Método 3: Deploy na VPS

1. **Envie o arquivo para sua VPS**:
```bash
scp royce-api.zip user@your-vps:/home/user/
```

2. **Na VPS, extraia e configure**:
```bash
ssh user@your-vps
unzip royce-api.zip
cd royce-api
cp .env.example .env
nano .env  # Configure suas API keys
```

3. **Instale Docker na VPS** (se não tiver):
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

4. **Execute com Docker Compose**:
```bash
docker-compose up -d
```

## 📡 Endpoints da API

### Status e Saúde

- `GET /` - Informações básicas da API
- `GET /health` - Status de saúde dos serviços
- `GET /docs` - Documentação interativa (Swagger UI)

### Produtos

#### Listar Todos os Produtos
```bash
GET /produtos?max_pages=30&items_per_page=200
```

**Resposta**:
```json
{
  "timestamp": "2025-01-15 10:30:00",
  "total_esperado": 4493,
  "total_coletado": 4450,
  "paginas_processadas": 23,
  "tempo_execucao": 145.5,
  "codigos": ["RC.600.021", "RC.600.022", ...],
  "problemas": {...}
}
```

#### Buscar Produto Específico
```bash
GET /produto/RC.600.021
```

**Resposta**:
```json
{
  "timestamp": "2025-01-15T10:30:00",
  "codigo_pesquisado": "RC.600.021",
  "encontrado": true,
  "dados": {
    "nome": "Compressor Modelo...",
    "descricao": "...",
    "url_imagem_tecnica": "...",
    "produtos_relacionados": [...]
  },
  "url_pesquisa": "https://www.royce.com.br/pesquisa?t=RC.600.021"
}
```

#### Processar JSON com Gemini
```bash
POST /produtos/json
Content-Type: application/json

{
  "source_data": {
    "dados": [{
      "codigo": "RC.600.021",
      "nome": "Compressor...",
      "descricao": "..."
    }]
  }
}
```

#### Processar Imagem
```bash
POST /pictures
Content-Type: multipart/form-data

file: [arquivo de imagem]
image_type: "technical" ou "normal" ou "auto"
enable_crop: true
apply_corner_dots: true
apply_rotation: true
```

#### Busca em Lote
```bash
POST /produtos/batch
Content-Type: application/json

{
  "codigos": ["RC.600.021", "RC.600.022", "RC.600.023"]
}
```

## 🔐 Configuração das API Keys

### Google Gemini API Key

1. Acesse: https://makersuite.google.com/app/apikey
2. Crie um novo projeto ou selecione um existente
3. Gere uma API Key
4. Adicione ao arquivo `.env`

### DashScope API Key

1. Acesse: https://dashscope.console.aliyun.com/
2. Crie uma conta (região internacional)
3. Gere uma API Key
4. Adicione ao arquivo `.env`

## 📁 Estrutura do Projeto

```
royce-api/
├── main.py                 # API principal
├── services/              # Serviços
│   ├── scraping_service.py
│   ├── product_service.py
│   ├── json_processor_service.py
│   └── image_processor_service.py
├── output/                # Arquivos processados
├── temp_uploads/          # Uploads temporários
├── logs/                  # Logs da aplicação
├── requirements.txt       # Dependências Python
├── .env.example          # Exemplo de configuração
├── Dockerfile            # Imagem Docker
├── docker-compose.yml    # Orquestração Docker
├── nginx.conf           # Configuração Nginx
└── README.md            # Este arquivo
```

## 🔍 Monitoramento e Logs

### Visualizar logs em tempo real:
```bash
# Local
tail -f logs/api.log

# Docker
docker-compose logs -f royce-api
```

### Verificar status:
```bash
curl http://localhost:8000/health
```

## 🚨 Solução de Problemas

### Erro: Chrome driver não encontrado

**Solução**: Instale o Chrome/Chromium:
```bash
# Ubuntu/Debian
sudo apt-get install chromium chromium-driver

# CentOS/RHEL
sudo yum install chromium
```

### Erro: API Key não configurada

**Solução**: Verifique o arquivo `.env`:
```bash
cat .env | grep API_KEY
```

### Erro: Porta 8000 já em uso

**Solução**: Mude a porta no `.env`:
```bash
API_PORT=8001
```

## 🔄 Backup e Restauração

### Backup dos dados:
```bash
tar -czf backup-$(date +%Y%m%d).tar.gz output/ logs/
```

### Restaurar backup:
```bash
tar -xzf backup-20250115.tar.gz
```

## 📊 Performance

### Recomendações de Hardware:

- **Mínimo**: 2 CPU cores, 2GB RAM
- **Recomendado**: 4 CPU cores, 4GB RAM
- **Produção**: 8 CPU cores, 8GB RAM

### Limites de Rate:

- Scraping: 2 requisições simultâneas
- Gemini API: ~60 req/min
- DashScope API: ~2 req/s

## 🔒 Segurança

1. **Sempre use HTTPS em produção**
2. **Mantenha as API keys seguras**
3. **Configure firewall adequadamente**
4. **Use nginx como reverse proxy**

### Configuração básica do Nginx:
```nginx
server {
    listen 80;
    server_name api.seudominio.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📝 Licença

Proprietário - 141AIR © 2025

## 🆘 Suporte

Para suporte, entre em contato através do sistema de issues ou diretamente com a equipe de desenvolvimento.

---

**Desenvolvido com ❤️ por 141AIR**