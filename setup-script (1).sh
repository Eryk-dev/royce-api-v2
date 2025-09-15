#!/bin/bash

# Royce API Setup Script
# Autor: 141AIR
# Data: 2025

set -e

echo "======================================"
echo "   Royce API - Script de Instalação   "
echo "======================================"
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para imprimir com cor
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Verificar se está rodando como root
if [[ $EUID -eq 0 ]]; then
   print_error "Este script não deve ser executado como root!"
   exit 1
fi

# Detectar sistema operacional
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    DISTRO=$(lsb_release -si 2>/dev/null || echo "unknown")
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    print_error "Sistema operacional não suportado: $OSTYPE"
    exit 1
fi

echo "Sistema detectado: $OS ($DISTRO)"
echo ""

# Verificar Python
echo "1. Verificando Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION encontrado"
else
    print_error "Python 3 não encontrado. Por favor, instale Python 3.11+"
    exit 1
fi

# Verificar Chrome/Chromium
echo ""
echo "2. Verificando Chrome/Chromium..."
if command -v chromium &> /dev/null || command -v chromium-browser &> /dev/null || command -v google-chrome &> /dev/null; then
    print_success "Chrome/Chromium encontrado"
else
    print_warning "Chrome/Chromium não encontrado"
    read -p "Deseja instalar Chromium agora? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [[ "$OS" == "linux" ]]; then
            if [[ "$DISTRO" == "Ubuntu" ]] || [[ "$DISTRO" == "Debian" ]]; then
                sudo apt-get update
                sudo apt-get install -y chromium chromium-driver
            elif [[ "$DISTRO" == "CentOS" ]] || [[ "$DISTRO" == "RedHat" ]]; then
                sudo yum install -y chromium
            else
                print_error "Instalação automática não disponível para $DISTRO"
                echo "Por favor, instale Chromium manualmente"
            fi
        elif [[ "$OS" == "macos" ]]; then
            if command -v brew &> /dev/null; then
                brew install --cask chromium
            else
                print_error "Homebrew não encontrado. Instale Chromium manualmente"
            fi
        fi
    fi
fi

# Criar ambiente virtual
echo ""
echo "3. Criando ambiente virtual Python..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_success "Ambiente virtual criado"
else
    print_warning "Ambiente virtual já existe"
fi

# Ativar ambiente virtual
source venv/bin/activate
print_success "Ambiente virtual ativado"

# Instalar dependências
echo ""
echo "4. Instalando dependências Python..."
pip install --upgrade pip
pip install -r requirements.txt
print_success "Dependências instaladas"

# Criar diretórios necessários
echo ""
echo "5. Criando estrutura de diretórios..."
mkdir -p output temp_uploads logs services
print_success "Diretórios criados"

# Configurar arquivo .env
echo ""
echo "6. Configurando variáveis de ambiente..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    print_success "Arquivo .env criado"
    echo ""
    print_warning "IMPORTANTE: Configure suas API Keys no arquivo .env"
    echo ""
    read -p "Deseja configurar as API Keys agora? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        read -p "Digite sua GEMINI_API_KEY: " GEMINI_KEY
        read -p "Digite sua DASHSCOPE_API_KEY: " DASHSCOPE_KEY
        
        # Substituir no arquivo .env
        if [[ "$OS" == "macos" ]]; then
            sed -i '' "s/your-gemini-api-key-here/$GEMINI_KEY/" .env
            sed -i '' "s/your-dashscope-api-key-here/$DASHSCOPE_KEY/" .env
        else
            sed -i "s/your-gemini-api-key-here/$GEMINI_KEY/" .env
            sed -i "s/your-dashscope-api-key-here/$DASHSCOPE_KEY/" .env
        fi
        
        print_success "API Keys configuradas"
    fi
else
    print_warning "Arquivo .env já existe"
fi

# Verificar Docker (opcional)
echo ""
echo "7. Verificando Docker (opcional)..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
    print_success "Docker $DOCKER_VERSION encontrado"
    
    if command -v docker-compose &> /dev/null; then
        DC_VERSION=$(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1)
        print_success "Docker Compose $DC_VERSION encontrado"
    else
        print_warning "Docker Compose não encontrado"
    fi
else
    print_warning "Docker não encontrado (opcional para deploy com containers)"
fi

# Criar script de inicialização
echo ""
echo "8. Criando scripts de inicialização..."
cat > start.sh << 'EOF'
#!/bin/bash
source venv/bin/activate
echo "Iniciando Royce API..."
python main.py
EOF
chmod +x start.sh
print_success "Script start.sh criado"

cat > start-daemon.sh << 'EOF'
#!/bin/bash
source venv/bin/activate
echo "Iniciando Royce API em background..."
nohup python main.py > logs/api.log 2>&1 &
echo $! > api.pid
echo "API iniciada com PID: $(cat api.pid)"
EOF
chmod +x start-daemon.sh
print_success "Script start-daemon.sh criado"

cat > stop.sh << 'EOF'
#!/bin/bash
if [ -f api.pid ]; then
    PID=$(cat api.pid)
    echo "Parando API (PID: $PID)..."
    kill $PID
    rm api.pid
    echo "API parada"
else
    echo "API não está rodando (arquivo api.pid não encontrado)"
fi
EOF
chmod +x stop.sh
print_success "Script stop.sh criado"

# Testar instalação
echo ""
echo "9. Testando instalação..."
python -c "import fastapi, selenium, google.generativeai, dashscope, PIL" 2>/dev/null
if [ $? -eq 0 ]; then
    print_success "Todas as bibliotecas foram importadas com sucesso"
else
    print_error "Erro ao importar bibliotecas. Verifique a instalação"
fi

# Resumo final
echo ""
echo "======================================"
echo "        Instalação Concluída!         "
echo "======================================"
echo ""
echo "Próximos passos:"
echo ""
echo "1. Configure suas API Keys (se ainda não fez):"
echo "   nano .env"
echo ""
echo "2. Inicie a API:"
echo "   ./start.sh          # Modo interativo"
echo "   ./start-daemon.sh   # Modo background"
echo ""
echo "3. Acesse a documentação:"
echo "   http://localhost:8000/docs"
echo ""
echo "4. Para parar a API (modo daemon):"
echo "   ./stop.sh"
echo ""

# Perguntar se deseja iniciar agora
read -p "Deseja iniciar a API agora? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    ./start.sh
fi