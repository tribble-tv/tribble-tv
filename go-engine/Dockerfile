FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY main.go ./
RUN go build -o /go-engine .

FROM alpine:3.20
COPY --from=build /go-engine /usr/local/bin/go-engine
ENV ENGINE_ADDR=:8080 MEDIA_ROOT=/media
EXPOSE 8080
CMD ["go-engine"]
