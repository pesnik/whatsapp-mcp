# ── Build ────────────────────────────────────────────────────────────────────
FROM golang:1.24-alpine AS builder

# CGO required for go-sqlite3
RUN apk add --no-cache gcc musl-dev

WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=1 GOOS=linux go build -trimpath -ldflags="-s -w" -o /bridge .

# ── Runtime ──────────────────────────────────────────────────────────────────
FROM alpine:3.21

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app
COPY --from=builder /bridge /app/bridge

# store/ holds whatsapp.db (session) and messages.db (history)
VOLUME ["/app/store"]

EXPOSE 8080

ENTRYPOINT ["/app/bridge"]
