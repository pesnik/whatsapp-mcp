package main

import (
	"testing"

	waProto "go.mau.fi/whatsmeow/binary/proto"
	"go.mau.fi/whatsmeow/proto/waCompanionReg"
	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/types"
	"google.golang.org/protobuf/proto"
)

func TestExtractTextContentIncludesCaptions(t *testing.T) {
	msg := &waProto.Message{ImageMessage: &waProto.ImageMessage{Caption: proto.String("see this @bot")}}
	if got := extractTextContent(msg); got != "see this @bot" {
		t.Fatalf("caption not extracted: %q", got)
	}
}

func TestContextInfoOfCoversMediaMessages(t *testing.T) {
	ctx := &waProto.ContextInfo{StanzaID: proto.String("Q1"), MentionedJID: []string{"123@lid"}}
	msg := &waProto.Message{VideoMessage: &waProto.VideoMessage{ContextInfo: ctx}}
	if got := contextInfoOf(msg).GetStanzaID(); got != "Q1" {
		t.Fatalf("context info not found on video message: %q", got)
	}
	if contextInfoOf(&waProto.Message{Conversation: proto.String("hi")}) != nil {
		t.Fatal("plain conversation has no context info")
	}
}

func TestSenderPhonePrefersPhoneJID(t *testing.T) {
	info := types.MessageInfo{MessageSource: types.MessageSource{
		Sender:    types.JID{User: "987", Server: types.HiddenUserServer},
		SenderAlt: types.JID{User: "8801700000000", Server: types.DefaultUserServer},
	}}
	if got := senderPhone(info); got != "8801700000000" {
		t.Fatalf("expected phone from SenderAlt, got %q", got)
	}
}

func TestConfigureDeviceIdentity(t *testing.T) {
	t.Setenv("WHATSAPP_DEVICE_NAME", "")
	configureDeviceIdentity()
	if got := store.DeviceProps.GetOs(); got != "AgentsHQ" {
		t.Fatalf("default device name: %q", got)
	}
	if store.DeviceProps.GetPlatformType() != waCompanionReg.DeviceProps_DESKTOP {
		t.Fatal("expected DESKTOP platform type")
	}
	t.Setenv("WHATSAPP_DEVICE_NAME", "Custom")
	configureDeviceIdentity()
	if got := store.DeviceProps.GetOs(); got != "Custom" {
		t.Fatalf("override not applied: %q", got)
	}
}
