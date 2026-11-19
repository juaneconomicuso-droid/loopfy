# Análise estática: extensão AutoLiveShop 1.0.15 (referência para o Loopfy)

Fonte: cópia instalada no Chrome (perfil Default, ID jhgjldacbjaplnglnlpmpbjnjihlbnip), JavaScript sem minificação.
Método: REA `analyze_javascript_application` (resumo) + leitura direta de `manifest.json`, `apibridge.js`, `fixador.js`, `license.js`, `background.js`, `popup.html`.
Nada foi executado. Evidência REA: `ev_5e02f45a2b804f694d4274de22b3ea56bc7fbab57ead89f6ca211b6528c2d9a6`.
Cobertura: o grafo do REA ficou parcial; a arquitetura abaixo vem da leitura dos arquivos citados. `content.js`, `carrinho.js`, `respostas.js`, `venda-chat.js` e `guardiao.js` foram só varridos, não lidos por inteiro.

## Arquitetura (observado)

- Extensão Manifest V3 que só atua em `shop.tiktok.com` e `seller-br.tiktok.com`.
  Permissões: storage, alarms, notifications, tabs, sidePanel. O painel é um side panel (`popup.html`).
- Dois mundos de execução:
  - `apibridge.js` roda no mundo da página (MAIN) e faz `fetch` assinado pela própria SPA do TikTok. É a ponte para as chamadas de API.
  - `content.js` + `motores/*` rodam no mundo isolado e pedem as chamadas à ponte por `postMessage` com token.
- Núcleo/motores (nomes dos arquivos): coletores (room, feed, ws, vitrine, tela), `fixador`, `mensagens`, `oferta`, `respostas`, `carrinho`, `venda-chat`, `guardiao`, `bloqueio-nome`, `chat-liberado`, `tempo-live`, `dinheiro`, `vitrine`, `espelho`.
- Endpoints internos usados (prefixo `/api/v1/streamer_desktop/`, não são API pública do TikTok Shop):
  `live_product/list` (GET), `live_product/pin` (op 1 = fixar, op 2 = desfixar), `live_room_info`, `user_activity_history`, `/api/v1/insights/...`, `webcast.tiktok.com/webcast/eco/violation_list/`.
- Fixador: modos contínuo, piscar e lista; produto escolhido ou aleatório. O card de fixação some em ~60 s, então renova no intervalo. O TikTok não expõe o estado de pin por API, então a extensão rastreia por conta própria o que fixou.
- Painel (rótulos da UI): live gravada, notificações de venda, conversão por produto, fixar automático/aleatório, recolocar sacolinha, mensagens automáticas, oferta relâmpago, respostas automáticas (chamar pelo nome), alerta de carrinho no chat, aviso de venda no chat, Bot Anti-Violação (encerra a live), bloqueio por nome, chat liberado, logs.
- Servidor próprio (autoliveshop.com.br):
  - `/api/live/state` publica o estado da live e devolve uma fila de ações remotas ("espelho" no celular/PWA).
  - `lic.autoliveshop.com.br` ativa licença: POST `/api/ativar {chave, machineId}` devolve token Ed25519 (~10 dias) conferido offline; teste grátis de 7 dias controlado pelo servidor por impressão da máquina.

## Fragilidades que o próprio código confirma
- Depende de endpoints internos não documentados e da assinatura da página. Há comentários de quebras reais: corpo vazio sem aviso, sacolinha alterada com a live no ar, rollout por conta.
- Fixação aceita pelo TikTok pode não ser aplicada, e não há como detectar.

## Decisões para o Loopfy
- Aproveitar: a arquitetura de extensão + painel lateral, o conjunto de motores, o espelho remoto e o licenciamento por token assinado.
- Não construir: a câmera virtual (`vcam.js`) para rodar vídeo gravado como se fosse live e o que for feito para esconder isso da plataforma.
  Manter o encerramento ao detectar violação, lendo o `violation_list`.
- Risco a decidir com o Juan: usar endpoints internos do Seller Center é zona cinza dos termos do TikTok. Aplicar só na conta do próprio usuário.
