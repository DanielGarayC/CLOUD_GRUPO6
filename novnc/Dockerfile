FROM python:3.9-alpine
RUN apk add --no-cache git bash
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc
RUN git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify
WORKDIR /opt/novnc
EXPOSE 6080
CMD ["/opt/novnc/utils/novnc_proxy", \
     "--listen", "0.0.0.0:6080", \
     "--auth-plugin", "TokenFile", \
     "--auth-source", "/opt/novnc/tokens", \
     "--web", "/opt/novnc"]