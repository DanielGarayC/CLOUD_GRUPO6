FROM python:3.9-alpine

RUN apk add --no-cache git bash python3 py3-pip

# 🔹 Clonar repos antiguos (estos sí tienen el plugin TokenFile)
RUN git clone https://github.com/kanaka/noVNC.git /opt/novnc
RUN git clone https://github.com/kanaka/websockify.git /opt/novnc/utils/websockify

# 🔹 Instalar numpy (para que no te salga el warning)
RUN pip install numpy

WORKDIR /opt/novnc
EXPOSE 6080

# 🔹 Arranque con soporte de tokens
CMD ["/opt/novnc/utils/novnc_proxy", "--listen", "6080","--vnc", "localhost:5900","--token-plugin", "websockify.token_plugins.TokenFile","--token-source", "/opt/novnc/tokens"]