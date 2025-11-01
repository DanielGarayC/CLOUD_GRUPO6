FROM alpine:latest
RUN apk add --no-cache git python3 py3-numpy
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc
RUN git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify
WORKDIR /opt/novnc
EXPOSE 6080
CMD ["./utils/novnc_proxy", "--vnc", "localhost:5900", "--listen", "6080"]