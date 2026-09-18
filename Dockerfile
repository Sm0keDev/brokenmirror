FROM alpine:3.19

RUN apk add --no-cache python3 py3-pip fuse nodejs
RUN echo "user_allow_other" >> /etc/fuse.conf

WORKDIR /opt/brokenmirror
COPY . .
RUN pip install --break-system-packages .

WORKDIR /app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["node", "index.js"]