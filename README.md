![Howl — lobo com fones neon sob uma lua cósmica](assets/howl-banner.png)

# Howl

Bot de rádios ao vivo para Discord, escrito em Python com discord.py e FFmpeg.

## Recursos

- `/radio`: painel com seletor de até 25 estações, Retomar, Parar e Desconectar.
- Retomar volta à última rádio tocada no servidor, sem precisar selecionar novamente.
- `/tocando`: consulta a estação atual.
- Reprodução independente por servidor e operações de voz serializadas.
- Controles disponíveis aos membros no mesmo canal de voz do bot.
- Desconexão automática quando não restam pessoas no canal.
- Reconexão de stream pelo FFmpeg; não há garantia de recuperação de todas as falhas.
- Menu em ordem alfabética, sem estação de demonstração.
- Buffer inicial de 2 segundos com fila limitada a 6 segundos de áudio e recomposição após oscilações.
- Troca de fonte no mesmo player: mantém a rádio anterior enquanto a próxima carrega.
- Última seleção tem prioridade; Parar cancela carregamentos pendentes.
- Links atualizados em segundo plano no Radio Browser, com cache e fallback para a URL salva.
- Não exige acesso ao conteúdo das mensagens.

## Executar no Windows

Requer Python 3.11 ou superior e FFmpeg instalado, disponível no PATH (ou caminho completo em `FFMPEG_PATH`).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

1. Crie uma aplicação e seu bot no [Discord Developer Portal](https://discord.com/developers/applications).
2. Coloque o token em `DISCORD_TOKEN` no `.env`. Nunca publique esse arquivo ou o token.
3. Os comandos são registrados globalmente. `DISCORD_GUILD_ID` não é mais usado; pode ser removido de configurações antigas. Após sincronizar os globais, o Howl remove as cópias de teste de `/radio` e `/tocando` dos servidores conectados. O Discord pode precisar ser recarregado para atualizar as sugestões.
4. Gere um convite com os escopos `bot` e `applications.commands`, com as permissões Ver canais, Enviar mensagens, Inserir links, Conectar e Falar. Não precisa de Administrador nem de Message Content Intent.
5. Configure pelo menos uma estação e execute:

```powershell
.\.venv\Scripts\python.exe bot.py
```

Entre em um canal de voz comum e use `/radio`.

## Estações

O menu contém onze rádios ativas, em ordem alfabética. Entre na call, execute `/radio` e selecione uma estação. Use Parar ou Desconectar para encerrar. O botão Retomar inicia novamente a última rádio tocada nesse servidor, inclusive após desconectar. Como é rádio ao vivo, volta ao conteúdo atual da transmissão, sem recuperar o trecho perdido.

Os novos painéis não expiram em 10 minutos e são registrados como views persistentes ao iniciar o bot. A memória da última estação é mantida durante a execução; após reiniciar o processo, selecione uma estação uma vez para habilitar novamente a retomada. Painéis antigos, criados antes da inclusão desse botão, precisam ser substituídos usando `/radio`.

O pacote `imageio-ffmpeg` fornece um executável de FFmpeg caso não haja um no PATH. `FFMPEG_PATH` continua permitindo escolher outro executável. Não é necessário instalar FFmpeg separadamente para o teste com as dependências completas.

`stations.json` inclui JB FM, CBN São Paulo e BBC World Service ativas. Seus streams públicos passaram por um teste curto de decodificação com FFmpeg em 15/10/2026. Disponibilidade e endereços podem mudar. Esse teste técnico não confirma autorização de retransmissão; essa autorização continua pendente para publicação do serviço.

Também inclui SomaFM Groove Salad, 89 FM A Rádio Rock, REYFM #LOFI e Radio Record. Seus links foram obtidos no Radio Browser, com `lastcheckok=1`, e testados localmente. Os UUIDs ficam em `radio_browser_uuid`. Esse estado é o último teste do diretório, não uma garantia de disponibilidade atual. Não indica licença de retransmissão, mesmo para emissoras sem anúncios.

Jovem Pan FM · Belo Horizonte, NPR · Program Stream e KEXP · Seattle também foram localizadas no Radio Browser e passaram por cinco segundos de teste em tempo real, sem esvaziar o buffer. A opção Jovem Pan usa a afiliada FM de BH, com música e entretenimento. A NPR usa seu stream de programas 24 horas; a KEXP oferece música alternativa e locução em inglês.

Ao selecionar uma estação, o Howl usa o endereço em cache e prepara aproximadamente 2 segundos de áudio antes de trocar a fonte no mesmo player. A rádio anterior continua tocando durante essa preparação; se a nova falhar, a anterior é mantida. Uma nova seleção cancela a preparação antiga, e Parar impede que uma seleção pendente inicie mais tarde. Na primeira seleção, o bot só entra na call depois de preparar o áudio.

A atualização de links acontece em segundo plano, com cache de 30 minutos e limite de 2,5 segundos por consulta. Se um endereço falhar, o bot tenta uma atualização e repete a preparação somente se receber uma URL diferente. Cada preparação tem espera de até 12 segundos pelo áudio; a conexão de voz usa timeout de 10 segundos, com limite externo de 12 segundos. São limites por etapa, não garantia de tempo total. A duração de cada seleção concluída aparece no log.

O buffer absorve oscilações curtas. Se a fila esvaziar, o bot envia silêncio até recompor o buffer, sem acelerar o áudio. Falhas persistentes da internet, da própria estação ou da conexão de voz ainda podem interromper a reprodução.

Para investigar travadas, observe o log `Buffer esvaziou`. Para testar a CBN sem Discord durante 30 segundos, execute:

```powershell
.\.venv\Scripts\python.exe check_streams.py --station cbn --seconds 30 --realtime
```

Esse teste verifica o caminho rádio → FFmpeg → buffer, sem testar a transmissão UDP para o Discord. No teste de desenvolvimento, a CBN completou 30 segundos sem esvaziar o buffer. Os testes automatizados simulam falta e retomada de áudio, fim da fonte, parada e indisponibilidade do Radio Browser:

```powershell
.\.venv\Scripts\python.exe -m unittest test_playback test_tuning -v
```

Referências: [Radio Browser API](https://docs.radio-browser.info/) e [opções HTTP de reconexão do FFmpeg](https://ffmpeg.org/ffmpeg-protocols.html#http).

Para repetir o diagnóstico técnico sem conectar ao Discord, execute `.\.venv\Scripts\python.exe check_streams.py`. Ele recebe dois segundos de cada stream, sem salvar o áudio.

Para adicionar uma fonte que você tenha autorização de transmitir, use:

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

A URL deve apontar para áudio HTTP(S) compatível com FFmpeg, não para uma página com player. Reinicie o bot após editar. Somente administradores do ambiente devem editar esse arquivo; usuários do Discord não podem fornecer URLs arbitrárias.

## Verificação manual

Com um stream autorizado configurado, confira: escolher uma estação; trocar durante reprodução; usar Parar e selecionar novamente; desconectar; tentar controlar de outro canal; duas pessoas selecionarem ao mesmo tempo; sair e deixar o canal vazio; usar uma URL indisponível; executar em dois servidores.

O bot espera o primeiro buffer antes de confirmar “Tocando”. Streams indisponíveis exibem uma mensagem de erro; consulte `/tocando` e os logs para diagnosticar falhas posteriores. Ainda não há metadados da música, favoritos ou reinício automático do processo após queda definitiva do stream.

## Referências

O canal Radio Paradise · Rock foi localizado no Radio Browser e validado com cinco segundos de reprodução sem esvaziar o buffer. O canal é identificado como Rock Mix no diretório e RockIt! no site da emissora.

Uma conta de bot conecta a apenas um canal de voz por servidor. Para reproduzir em duas calls do mesmo servidor ao mesmo tempo, são necessárias duas contas de bot distintas. O mesmo Howl pode atender servidores diferentes simultaneamente.

- [discord.py: instalação](https://discordpy.readthedocs.io/en/stable/intro.html)
- [discord.py: API de voz](https://discordpy.readthedocs.io/en/stable/api.html#voice)
