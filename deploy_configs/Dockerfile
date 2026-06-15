FROM docker.m.daocloud.io/library/node:20-alpine

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories

RUN apk add --no-cache python3 py3-pip make g++ bash tzdata \
    && ln -sf python3 /usr/bin/python \
    && rm -rf /var/cache/apk/*

ENV TZ=Asia/Shanghai
RUN cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

WORKDIR /app

COPY package*.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm install --production

COPY deploy_configs/requirements.txt ./
RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY . .

EXPOSE 8787

CMD ["node", "server.js"]
