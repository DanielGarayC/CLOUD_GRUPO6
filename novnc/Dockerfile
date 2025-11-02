FROM python:3.9-alpine

RUN apk add --no-cache git bash python3 py3-pip openssl

# 🔹 Clonar repos antiguos (estos sí tienen el plugin TokenFile)
RUN git clone https://github.com/kanaka/noVNC.git /opt/novnc \
 && git clone https://github.com/kanaka/websockify.git /opt/novnc/utils/websockify

# 🔹 Instalar websockify como módulo de Python (para poder usar `-m websockify`)
RUN pip install /opt/novnc/utils/websockify

# 🔹 Instalar numpy (para evitar warning)
RUN pip install numpy

# 🔹 Crear certificado dummy (opcional, evita warning de self.pem)
RUN openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout /opt/novnc/self.pem -out /opt/novnc/self.pem \
    -days 365 -subj "/CN=novnc"

WORKDIR /opt/novnc
EXPOSE 6080

# 🔹 Arranque con soporte de tokens
CMD ["python3", "-m", "websockify", "6080","--web", "/opt/novnc","--token-plugin", "websockify.token_plugins.TokenFile","--token-source", "/opt/novnc/tokens"]
