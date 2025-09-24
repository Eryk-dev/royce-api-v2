# Configuração de OCR para Detecção de Código de Fornecedor

## Instalação do Tesseract (Opcional)

A API pode detectar e remover automaticamente códigos de fornecedor no formato "000.000" no canto inferior direito das imagens. Para melhor precisão, recomenda-se instalar o Tesseract OCR.

### macOS
```bash
brew install tesseract
brew install tesseract-lang  # Idiomas adicionais (opcional)
```

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install tesseract-ocr
sudo apt install tesseract-ocr-por  # Português (opcional)
```

### Windows
1. Baixe o instalador de: https://github.com/UB-Mannheim/tesseract/wiki
2. Execute o instalador
3. Adicione o caminho de instalação ao PATH do sistema

### Verificar Instalação
```bash
tesseract --version
```

## Instalação das Dependências Python

```bash
pip install pytesseract==0.3.10
pip install opencv-python==4.10.0.84
```

## Configuração via Variáveis de Ambiente

Configure o comportamento da detecção de código através das seguintes variáveis:

```bash
# Habilitar/Desabilitar detecção de código (padrão: true)
ENABLE_SUPPLIER_CODE_DETECTION=true

# Percentual da altura da imagem para buscar código (parte inferior)
SUPPLIER_CODE_BOTTOM_PERCENT=0.25  # 25% inferior

# Percentual da largura da imagem para buscar código (parte direita)  
SUPPLIER_CODE_RIGHT_PERCENT=0.4    # 40% direita
```

## Funcionamento

1. **Com Tesseract instalado**: O sistema usa OCR para detectar precisamente o código "000.000"
2. **Sem Tesseract**: O sistema usa análise de contornos para detectar possíveis áreas de texto
3. **Fallback**: Se nenhuma detecção funcionar, aplica retângulo em posição fixa

## Logs

O sistema registra as seguintes informações:
- Quando um código é detectado via OCR
- Quando um código é detectado via contornos
- Quando o fallback de posição fixa é usado
- Coordenadas exatas onde o retângulo branco foi aplicado

## Desabilitar Detecção

Para desabilitar completamente a detecção automática:

```bash
export ENABLE_SUPPLIER_CODE_DETECTION=false
```

Neste caso, apenas o retângulo de posição fixa será aplicado.
