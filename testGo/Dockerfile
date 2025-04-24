FROM golang:1.24-alpine

WORKDIR /app

RUN apk add --no-cache git gcc musl-dev curl

ENV CGO_ENABLED=1
ENV GOCACHE=/app/.cache/go-build
ENV GOMODCACHE=/app/.cache/go-mod
ENV XDG_CONFIG_HOME=/app/.config

COPY go.* ./
RUN go mod download
COPY . .


RUN go get entgo.io/ent/cmd/ent
RUN go mod download

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]