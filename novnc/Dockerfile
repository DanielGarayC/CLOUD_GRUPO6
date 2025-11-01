FROM python:3.9-alpine
RUN apk add --no-cache git bash
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc
RUN git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify
WORKDIR /opt/novnc
EXPOSE 6080
CMD ["/opt/novnc/utils/novnc_proxy", "--vnc", "localhost:5900", "--listen", "6080"]