![Howl — lobo com fones neon sob uma lua cósmica](assets/howl-banner.png)



https://github.com/user-attachments/assets/e435d61a-b3c2-4539-adcf-682cc9cd3429



# Howl

Rádios ao vivo no Discord. Entre em um canal de voz, use `/radio` e escolha uma estação para ouvir com seus amigos.

Projeto pessoal de portfólio, sem fins lucrativos, desenvolvido em **Python com discord.py e FFmpeg**. A instalação mantida pelo autor é utilizada apenas em servidores privados. Este repositório apresenta a implementação; não oferece um serviço público de retransmissão nem um convite público para o bot.

## Funcionalidades

- `/radio`: painel com uma lista de estações em ordem alfabética, sem filtros por categoria.
- **Retomar**: volta à última rádio tocada no servidor, inclusive após desconectar.
- **Parar**: encerra a reprodução e cancela carregamentos pendentes.
- **Desconectar**: retira o Howl do canal de voz.
- `/tocando`: informa a estação atual.
- A rádio anterior continua tocando enquanto a próxima é preparada; se o carregamento falhar, a fonte anterior é mantida.
- Uma nova seleção substitui a solicitação de carregamento anterior.
- Controles restritos aos membros no mesmo canal de voz do bot.
- Desconexão automática quando não restam pessoas no canal.
- Reprodução independente em servidores diferentes.
- Painéis persistentes, sem expiração de 10 minutos.
- Não exige acesso ao conteúdo das mensagens.

**Retomar acompanha o momento atual da transmissão ao vivo.** Não recupera o trecho perdido. A última estação fica na memória durante a execução; após reiniciar o processo, é necessário selecionar uma estação novamente.

Uma conta de bot pode ocupar apenas um canal de voz por servidor. Para tocar em duas calls do mesmo servidor simultaneamente, seriam necessárias duas contas de bot distintas.

## Tecnologias e funcionamento

| Componente | Responsabilidade |
| --- | --- |
| Python e asyncio | Comandos, tarefas assíncronas e coordenação por servidor |
| discord.py com suporte a voz | Integração com Discord, painel e envio de áudio |
| FFmpeg | Recepção dos streams e conversão para Opus |
| Radio Browser | Atualização de endereços para estações com UUID cadastrado |
| python-dotenv | Configuração local por variáveis de ambiente |

O áudio passa por um buffer inicial de aproximadamente 2 segundos, com fila limitada a 6 segundos. A próxima estação é preparada em segundo plano e substitui a fonte no mesmo player somente quando há áudio pronto. Encerrar processos de áudio acontece fora do loop de eventos do Discord.

Para as estações com UUID do Radio Browser, os links são atualizados em segundo plano, com cache de 30 minutos e fallback para o endereço salvo. As demais usam a URL configurada em `stations.json`. A 98 FM Rio usa o endereço publicado no player oficial, pois não foi encontrada no diretório.

O FFmpeg tenta recuperar falhas temporárias de conexão. Se o buffer esvaziar, o player envia silêncio enquanto recompõe a fila. Isso reduz o impacto de oscilações curtas, mas não garante continuidade quando a própria rádio, a internet ou a conexão de voz falham.

## Executar no Windows

Requer **Python 3.11 ou superior**, uma aplicação de bot no Discord e conexão à internet. O pacote `imageio-ffmpeg`, incluído nas dependências, fornece um executável de FFmpeg caso não haja um disponível no PATH. Uma instalação separada é opcional.

Na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Na primeira configuração, crie o arquivo `.env` a partir do exemplo. Se já existir, edite o arquivo atual:

```powershell
Copy-Item .env.example .env
```

Preencha o token localmente:

```env
DISCORD_TOKEN=seu_token_do_bot
FFMPEG_PATH=ffmpeg
```

1. Crie a aplicação e o bot no [Discord Developer Portal](https://discord.com/developers/applications).
2. No convite, selecione os escopos `bot` e `applications.commands` e as permissões **Ver canais, Enviar mensagens, Inserir links, Conectar e Falar**. Administrador e Message Content Intent não são necessários.
3. Adicione o bot ao servidor privado em que será usado.
4. Inicie o processo:

```powershell
.\.venv\Scripts\python.exe bot.py
```

Mantenha o processo em execução. Para reiniciar, pressione **Ctrl+C** e execute o comando novamente. Não publique o token nem o arquivo `.env`; ele está incluído no `.gitignore`.

Os comandos são registrados globalmente e podem levar algum tempo para aparecer no Discord. `DISCORD_GUILD_ID` não é mais usado. Depois de sincronizar os globais, o Howl remove as cópias antigas de teste dos seus comandos nos servidores conectados, evitando sugestões duplicadas.

Se quiser usar outro FFmpeg, defina o caminho completo em `FFMPEG_PATH`.

## Estações configuradas

O catálogo atual contém 16 estações. Os perfis abaixo descrevem as opções do menu; a programação pode variar por horário.

| Estação | Perfil |
| --- | --- |
| 89 FM A Rádio Rock | Rock · São Paulo |
| 98 FM Rio | Música, flashbacks e entretenimento · Rio |
| BandNews FM · Rio de Janeiro | Notícias em português |
| BBC World Service | Notícias internacionais em inglês |
| CBN São Paulo | Notícias em português |
| CNN International | Notícias internacionais em inglês |
| JB FM · 99,9 Rio | Música brasileira e internacional |
| Jovem Pan FM · Belo Horizonte | Música e entretenimento |
| KEXP · Seattle | Música alternativa e locução em inglês |
| NPR · Program Stream | Notícias e programas em inglês |
| Rádio Cidade · Rio de Janeiro | Rock nacional e internacional |
| Radio Paradise · Rock | Rock internacional |
| Radio Record | Eletrônica e dance · russo |
| REYFM #LOFI | Lo-fi para estudar e relaxar |
| SomaFM Groove Salad | Eletrônica ambiente |
| TMC · antiga Transamérica · São Paulo | Notícias e esportes |

Os endereços ficam em [stations.json](stations.json). Links e disponibilidade podem mudar. Os testes de áudio realizados no desenvolvimento confirmam apenas funcionamento técnico, não autorização de retransmissão. Consulte [Uso e direitos](#uso-e-direitos).

Para cadastrar uma fonte cuja transmissão você tenha autorização de realizar, adicione um objeto à lista:

```json
{
  "id": "minha-radio",
  "name": "Minha Rádio",
  "category": "Música",
  "url": "https://seu-servidor.example/live.mp3",
  "website": "https://seu-servidor.example",
  "enabled": true
}
```

O campo `category` é uma descrição exibida no seletor, sem criar categorias no painel. A URL deve apontar para áudio HTTP(S) compatível com FFmpeg, não para uma página com player. Quando houver um registro no Radio Browser, o campo opcional `radio_browser_uuid` permite atualizar seu endereço.

Reinicie o bot após editar o catálogo. O menu suporta até 25 estações ativas. Somente quem administra a instalação deve editar esse arquivo; usuários do Discord não podem fornecer URLs arbitrárias pelo painel.

## Testes e diagnóstico

Os testes locais cobrem buffer, troca de estação, cancelamento, retomada, falhas de consulta e limpeza dos comandos de teste. Não exigem token nem conexão ao Discord:

```powershell
.\.venv\Scripts\python.exe -m unittest test_playback test_tuning test_commands -v
```

Para verificar os streams do catálogo, recebendo uma pequena amostra sem gravar áudio:

```powershell
.\.venv\Scripts\python.exe check_streams.py
```

Para acompanhar a CBN durante 30 segundos em tempo real:

```powershell
.\.venv\Scripts\python.exe check_streams.py --station cbn --seconds 30 --realtime
```

Esse diagnóstico verifica o caminho **rádio → FFmpeg → buffer**. Não testa a transmissão de voz para o Discord. Em caso de travadas, observe mensagens como `Buffer esvaziou` e erros do FFmpeg no terminal. O log também registra o tempo de preparação de uma estação.

No Discord, verifique a seleção e a troca de rádio, Parar/Retomar, Desconectar, a saída automática do canal vazio e a restrição de controle a membros no mesmo canal.

## Limitações atuais

- A retomada depende da última estação guardada na memória do processo.
- Não há gravação da programação, busca por músicas, favoritos ou metadados da faixa atual.
- O bot não reinicia o processo de áudio automaticamente após uma falha definitiva do stream; é necessário selecionar ou retomar a estação.
- O tempo para começar depende da resposta do stream e da conexão de voz; os timeouts são limites por etapa, não uma garantia de tempo total.

## Uso e direitos

As transmissões, músicas, marcas e demais conteúdos pertencem às respectivas emissoras e titulares. O Howl não representa essas emissoras nem afirma possuir vínculo ou autorização delas.

O projeto é pessoal, sem fins lucrativos, e a instalação do autor é usada em servidores privados. Essas condições, os créditos e a presença de um stream no Radio Browser **não substituem autorização de retransmissão**. As permissões não foram confirmadas para todo o catálogo. A [política da 98 FM Rio](https://98fmrio.com/direitos-autorais-conteudos-musicais-licenciados/) contém restrições ao uso da programação fora dos canais oficiais; também não foi confirmada uma licença de retransmissão da CNN International.

Publicar este código e operar um serviço de retransmissão são atividades distintas. Para demonstrações de portfólio, podem ser usadas fontes próprias ou com licença que permita a transmissão pretendida.

**Solicitações de remoção:** detentores de direitos podem entrar em contato pelo [repositório do Howl no GitHub](https://github.com/AlexanderRevoredo/Howl-Discord), identificando a estação, o conteúdo afetado e o motivo da solicitação.

## Referências

- [discord.py: instalação](https://discordpy.readthedocs.io/en/stable/intro.html)
- [discord.py: API de voz](https://discordpy.readthedocs.io/en/stable/api.html#voice)
- [Radio Browser API](https://docs.radio-browser.info/)
- [FFmpeg: protocolos e opções de reconexão](https://ffmpeg.org/ffmpeg-protocols.html#http)
