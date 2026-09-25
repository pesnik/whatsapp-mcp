package main

import (
	"context"
	"math/rand"
	"os"
	"sync"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waCompanionReg"
	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/types"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"
)

// configureDeviceIdentity sets how this linked device appears on the phone
// (Settings → Linked devices). whatsmeow's default is "whatsmeow" with an
// unknown platform. Only sent in the pairing payload: an already-linked
// device keeps the name it was paired with until it is re-linked.
func configureDeviceIdentity() {
	name := os.Getenv("WHATSAPP_DEVICE_NAME")
	if name == "" {
		name = "AgentsHQ"
	}
	store.DeviceProps.Os = proto.String(name)
	// DESKTOP renders the plain name (a browser type would prefix it,
	// e.g. "Chrome (AgentsHQ)").
	store.DeviceProps.PlatformType = waCompanionReg.DeviceProps_DESKTOP.Enum()
}

// presenceKeeper keeps this device's presence honest and its "last active"
// fresh without looking permanently online.
//
// A companion that never sends presence is never "active" as far as
// WhatsApp is concerned: the phone's Linked devices list shows a stale
// "last active", and WhatsApp unlinks companions after ~30 days of
// inactivity. Being "available" has a cost too: while a companion is online
// the phone stops showing notifications, and an account online 24/7 looks
// automated. So the keeper goes available briefly -- on connect, on a
// jittered heartbeat, and while the bot is actually working (typing,
// sending) -- then back to unavailable.
type presenceKeeper struct {
	client *whatsmeow.Client
	log    waLog.Logger

	mu          sync.Mutex
	online      bool
	onlineUntil time.Time
	manual      bool // held online by an explicit POST /api/presence {available:true}
	timer       *time.Timer
}

const (
	heartbeatPulse = 45 * time.Second
	defaultBeat    = 6 * time.Hour
)

func newPresenceKeeper(client *whatsmeow.Client, log waLog.Logger) *presenceKeeper {
	return &presenceKeeper{client: client, log: log}
}

// activeFor marks the device online for at least d from now.
func (p *presenceKeeper) activeFor(d time.Duration) {
	p.mu.Lock()
	defer p.mu.Unlock()
	until := time.Now().Add(d)
	if until.After(p.onlineUntil) {
		p.onlineUntil = until
	}
	if !p.online {
		if err := p.client.SendPresence(context.Background(), types.PresenceAvailable); err != nil {
			// ErrNoPushName right after pairing: the push name arrives via
			// app-state sync, and onPushName() retries then.
			p.log.Warnf("presence: going available failed: %v", err)
			return
		}
		p.online = true
	}
	p.scheduleLocked()
}

// setManual is the explicit agent/tool switch (POST /api/presence).
func (p *presenceKeeper) setManual(available bool) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.manual = available
	state := types.PresenceUnavailable
	if available {
		state = types.PresenceAvailable
	}
	if err := p.client.SendPresence(context.Background(), state); err != nil {
		return err
	}
	p.online = available
	if !available {
		p.onlineUntil = time.Time{}
	}
	p.scheduleLocked()
	return nil
}

func (p *presenceKeeper) scheduleLocked() {
	if p.timer != nil {
		p.timer.Stop()
		p.timer = nil
	}
	if !p.online || p.manual {
		return
	}
	p.timer = time.AfterFunc(time.Until(p.onlineUntil), p.expire)
}

func (p *presenceKeeper) expire() {
	p.mu.Lock()
	defer p.mu.Unlock()
	if !p.online || p.manual {
		return
	}
	if wait := time.Until(p.onlineUntil); wait > 0 {
		p.scheduleLocked() // extended since this timer was armed
		return
	}
	if err := p.client.SendPresence(context.Background(), types.PresenceUnavailable); err != nil {
		p.log.Warnf("presence: going unavailable failed: %v", err)
	}
	p.online = false
}

// onConnected: whatsmeow asks for at least one SendPresence after every
// connect so the server has our push name; pulse once.
func (p *presenceKeeper) onConnected() {
	p.mu.Lock()
	p.online = false // a new connection starts with no presence sent
	p.mu.Unlock()
	p.activeFor(heartbeatPulse)
}

// onPushName retries the pulse that fails with ErrNoPushName right after pairing.
func (p *presenceKeeper) onPushName() { p.activeFor(heartbeatPulse) }

// runHeartbeat pulses every WHATSAPP_PRESENCE_HEARTBEAT (default 6h, ±25%
// jitter; "0" disables) so a quiet bot still counts as an active device.
func (p *presenceKeeper) runHeartbeat() {
	every := defaultBeat
	if v := os.Getenv("WHATSAPP_PRESENCE_HEARTBEAT"); v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			p.log.Warnf("presence: invalid WHATSAPP_PRESENCE_HEARTBEAT %q, using %s", v, defaultBeat)
		} else {
			every = d
		}
	}
	if every <= 0 {
		return
	}
	for {
		jitter := time.Duration((rand.Float64() - 0.5) * 0.5 * float64(every))
		time.Sleep(every + jitter)
		if p.client.IsConnected() {
			p.activeFor(heartbeatPulse)
		}
	}
}
