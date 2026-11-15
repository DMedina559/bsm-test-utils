package main

import (
	"bytes"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func captureOutput(fn func()) (string, string) {
	oldOut := os.Stdout
	oldErr := os.Stderr
	rOut, wOut, _ := os.Pipe()
	rErr, wErr, _ := os.Pipe()
	os.Stdout = wOut
	os.Stderr = wErr

	fn()

	_ = wOut.Close()
	_ = wErr.Close()
	os.Stdout = oldOut
	os.Stderr = oldErr

	var bufOut, bufErr bytes.Buffer
	_, _ = io.Copy(&bufOut, rOut)
	_, _ = io.Copy(&bufErr, rErr)
	return bufOut.String(), bufErr.String()
}

func TestSaveLifecycleAndPolls(t *testing.T) {
	cfg := ServerConfig{
		SaveReadyPolls: 2,
		LevelName:      "TestWorld",
	}
	state := newServerState(cfg)

	// Query before hold fails
	out, _ := captureOutput(func() {
		state.processCommand("save query")
	})
	if !strings.Contains(out, "Save has not been held.") {
		t.Fatalf("expected save not held error, got: %s", out)
	}

	// Hold
	out, _ = captureOutput(func() {
		state.processCommand("save hold")
	})
	if !strings.Contains(out, "Saving...") {
		t.Fatalf("expected Saving..., got: %s", out)
	}

	// First query -> in progress
	out, _ = captureOutput(func() {
		state.processCommand("save query")
	})
	if !strings.Contains(out, "The save is in progress...") {
		t.Fatalf("expected save in progress on first poll, got: %s", out)
	}

	// Second query -> ready + file list
	out, _ = captureOutput(func() {
		state.processCommand("save query")
	})
	if !strings.Contains(out, "Data saved. Files are now ready to be copied.") {
		t.Fatalf("expected data saved message, got: %s", out)
	}
	if !strings.Contains(out, "TestWorld/db/000003.ldb:1240") {
		t.Fatalf("expected file list for TestWorld, got: %s", out)
	}

	// Resume
	out, _ = captureOutput(func() {
		state.processCommand("save resume")
	})
	if !strings.Contains(out, "Changes to the level are resumed.") {
		t.Fatalf("expected save resumed message, got: %s", out)
	}
}

func TestPlayerIdentityAndSpaces(t *testing.T) {
	name1, xuid1, pfid1 := parsePlayerArgs(`"Steve The Builder"`)
	if name1 != "Steve The Builder" {
		t.Fatalf("expected name 'Steve The Builder', got %q", name1)
	}
	name2, xuid2, pfid2 := parsePlayerArgs(`"Alex The Explorer"`)
	if name2 != "Alex The Explorer" {
		t.Fatalf("expected name 'Alex The Explorer', got %q", name2)
	}
	if xuid1 == xuid2 || pfid1 == pfid2 {
		t.Fatalf("expected distinct IDs for different players, got (%s, %s) vs (%s, %s)", xuid1, pfid1, xuid2, pfid2)
	}

	// Explicit override
	name3, xuid3, pfid3 := parsePlayerArgs(`"Custom Player" xuid=1111222233334444 pfid=AABBCCDDEEFF0011`)
	if name3 != "Custom Player" || xuid3 != "1111222233334444" || pfid3 != "AABBCCDDEEFF0011" {
		t.Fatalf("unexpected override parse: %s %s %s", name3, xuid3, pfid3)
	}
}

func TestCommandRecordingAndStopControl(t *testing.T) {
	tmpDir := t.TempDir()
	cmdLog := filepath.Join(tmpDir, "commands.log")
	cfg := ServerConfig{
		IgnoreStop:     true,
		ExitCode:       42,
		CommandLogFile: cmdLog,
	}
	state := newServerState(cfg)

	state.recordCommand("save hold")
	state.processCommand("save hold")

	state.recordCommand("stop")
	shouldExit, _ := state.processCommand("stop")
	if shouldExit {
		t.Fatalf("expected stop to be ignored when IgnoreStop is true")
	}

	state.processCommand("__DUMMY__ SET_IGNORE_STOP false")
	shouldExit, code := state.processCommand("stop")
	if !shouldExit || code != 42 {
		t.Fatalf("expected exit=true code=42, got exit=%v code=%d", shouldExit, code)
	}

	data, err := os.ReadFile(cmdLog)
	if err != nil {
		t.Fatalf("failed reading command log: %v", err)
	}
	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	if len(lines) != 2 || lines[0] != "save hold" || lines[1] != "stop" {
		t.Fatalf("unexpected recorded commands: %v", lines)
	}
}

func TestLiveBackupMutation(t *testing.T) {
	tmpDir := t.TempDir()
	mutateTarget := filepath.Join(tmpDir, "worlds", "Bedrock level", "db", "live.ldb")
	cfg := ServerConfig{
		SaveMutateFile: mutateTarget,
	}
	state := newServerState(cfg)

	captureOutput(func() {
		state.processCommand("save hold")
		state.processCommand("save query")
	})

	content, err := os.ReadFile(mutateTarget)
	if err != nil {
		t.Fatalf("expected mutated file to exist: %v", err)
	}
	if !strings.Contains(string(content), "live-backup-mutation-") {
		t.Fatalf("unexpected mutated file content: %s", string(content))
	}
}
