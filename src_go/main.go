package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

type ServerConfig struct {
	MockCrash      bool
	StartupFailure bool
	NeverReady     bool
	StartupDelayMs int
	StopDelayMs    int
	IgnoreStop     bool
	ExitCode       int
	CrashExitCode  int
	CrashAfterMs   int
	SaveReadyPolls int
	SaveHoldFail   bool
	SaveQueryFail  bool
	SaveResumeFail bool
	SaveMutateFile string
	LevelName      string
	CommandLogFile string
	SaveFilesCsv   string
}

type ServerState struct {
	mu               sync.Mutex
	config           ServerConfig
	saveHeld         bool
	saveQueryCount   int
	ignoreStop       bool
	stopDelayMs      int
	saveReadyPolls   int
	saveQueryFail    bool
	saveResumeFail   bool
	saveHoldFail     bool
	receivedCommands []string
}

func newServerState(cfg ServerConfig) *ServerState {
	return &ServerState{
		config:         cfg,
		ignoreStop:     cfg.IgnoreStop,
		stopDelayMs:    cfg.StopDelayMs,
		saveReadyPolls: cfg.SaveReadyPolls,
		saveQueryFail:  cfg.SaveQueryFail,
		saveResumeFail: cfg.SaveResumeFail,
		saveHoldFail:   cfg.SaveHoldFail,
	}
}

func (s *ServerState) recordCommand(cmd string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.receivedCommands = append(s.receivedCommands, cmd)
	if s.config.CommandLogFile != "" {
		f, err := os.OpenFile(s.config.CommandLogFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
		if err == nil {
			_, _ = f.WriteString(cmd + "\n")
			_ = f.Close()
		}
	}
}

func (s *ServerState) getSaveFileList() string {
	if s.config.SaveFilesCsv != "" {
		return s.config.SaveFilesCsv
	}
	lvl := s.config.LevelName
	if lvl == "" {
		lvl = "Bedrock level"
	}
	return fmt.Sprintf(
		"%s/db/000003.ldb:1240, %s/db/MANIFEST-000002:192, %s/level.dat:2048, %s/levelname.txt:13",
		lvl, lvl, lvl, lvl,
	)
}

func (s *ServerState) mutateLiveFileIfConfigured() {
	if s.config.SaveMutateFile == "" {
		return
	}
	dir := filepath.Dir(s.config.SaveMutateFile)
	if dir != "." && dir != "" {
		_ = os.MkdirAll(dir, 0755)
	}
	f, err := os.OpenFile(s.config.SaveMutateFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err == nil {
		_, _ = fmt.Fprintf(f, "live-backup-mutation-%d\n", time.Now().UnixNano())
		_ = f.Close()
	}
}

func deterministicIDs(name string) (string, string) {
	sum := sha256.Sum256([]byte(name))
	// 16-digit numeric XUID derived from hash
	var xuidVal uint64
	for i := 0; i < 8; i++ {
		xuidVal = (xuidVal << 8) | uint64(sum[i])
	}
	xuid := fmt.Sprintf("%016d", (xuidVal%9000000000000000)+1000000000000000)
	pfid := strings.ToUpper(hex.EncodeToString(sum[8:16]))
	return xuid, pfid
}

func parsePlayerArgs(rest string) (string, string, string) {
	rest = strings.TrimSpace(rest)
	if rest == "" {
		return "DummyPlayer", "2535413537906883", "94BDCFBEDC749828"
	}
	var name string
	var tokens []string
	if strings.HasPrefix(rest, "\"") {
		endIdx := strings.Index(rest[1:], "\"")
		if endIdx != -1 {
			name = rest[1 : endIdx+1]
			remainder := strings.TrimSpace(rest[endIdx+2:])
			if remainder != "" {
				tokens = strings.Fields(remainder)
			}
		} else {
			name = strings.TrimPrefix(rest, "\"")
		}
	} else {
		fields := strings.Fields(rest)
		// Check if last tokens are xuid=... or pfid=...
		var nameParts []string
		for _, tok := range fields {
			if strings.HasPrefix(tok, "xuid=") || strings.HasPrefix(tok, "pfid=") {
				tokens = append(tokens, tok)
			} else {
				nameParts = append(nameParts, tok)
			}
		}
		name = strings.Join(nameParts, " ")
	}
	if name == "" {
		name = "DummyPlayer"
	}
	xuid, pfid := deterministicIDs(name)
	if name == "DummyPlayer" {
		xuid = "2535413537906883"
		pfid = "94BDCFBEDC749828"
	}
	for _, tok := range tokens {
		if strings.HasPrefix(tok, "xuid=") {
			xuid = strings.TrimPrefix(tok, "xuid=")
		} else if strings.HasPrefix(tok, "pfid=") {
			pfid = strings.TrimPrefix(tok, "pfid=")
		}
	}
	return name, xuid, pfid
}

func main() {
	var cfg ServerConfig
	flag.BoolVar(&cfg.MockCrash, "mock-crash", false, "Simulate a server crash immediately upon startup")
	flag.BoolVar(&cfg.StartupFailure, "startup-failure", false, "Simulate a fatal startup failure before world load")
	flag.BoolVar(&cfg.NeverReady, "never-ready", false, "Start up without ever emitting 'Server started.'")
	flag.IntVar(&cfg.StartupDelayMs, "startup-delay-ms", 1000, "Delay in ms for each startup phase")
	flag.IntVar(&cfg.StopDelayMs, "stop-delay-ms", 0, "Delay in ms before exiting on stop")
	flag.BoolVar(&cfg.IgnoreStop, "ignore-stop", false, "Ignore the 'stop' command")
	flag.IntVar(&cfg.ExitCode, "exit-code", 0, "Exit code on normal stop")
	flag.IntVar(&cfg.CrashExitCode, "crash-exit-code", 1, "Exit code on crash")
	flag.IntVar(&cfg.CrashAfterMs, "crash-after-ms", 0, "Automatically crash after N ms of runtime")
	flag.IntVar(&cfg.SaveReadyPolls, "save-ready-polls", 1, "Number of 'save query' polls before files are ready")
	flag.BoolVar(&cfg.SaveHoldFail, "save-hold-fail", false, "Fail on 'save hold'")
	flag.BoolVar(&cfg.SaveQueryFail, "save-query-fail", false, "Fail on 'save query'")
	flag.BoolVar(&cfg.SaveResumeFail, "save-resume-fail", false, "Fail on 'save resume'")
	flag.StringVar(&cfg.SaveMutateFile, "save-mutate-file", "", "File path to modify during save hold/query")
	flag.StringVar(&cfg.LevelName, "level-name", "Bedrock level", "World level name")
	flag.StringVar(&cfg.CommandLogFile, "command-log-file", "", "File path to append received stdin commands")
	flag.StringVar(&cfg.SaveFilesCsv, "save-files", "", "Custom file list returned by save query")
	flag.Parse()

	if cfg.MockCrash {
		logPrint("ERROR", "CRASH: Segfault simulating server failure")
		os.Exit(cfg.CrashExitCode)
	}

	// Startup sequence matching real logs
	fmt.Println("NO LOG FILE! - setting up server logging...")
	logPrint("INFO", "Starting Server")
	logPrint("INFO", "Version: 1.26.60-beta21")
	logPrint("INFO", "Session ID: 6b064b06-168e-4046-9513-650e6867dffd")
	logPrint("INFO", "Build ID: 50366992")
	logPrint("INFO", "Branch: preview/hotfix_26u6-1")
	logPrint("INFO", "Commit ID: 087a0f136047555266e79ccbb908e0ea5135c9e6")
	logPrint("INFO", "Configuration: Publish")
	logPrint("INFO", "Contents of server.properties: {}")
	logPrint("INFO", fmt.Sprintf("Level Name: %s", cfg.LevelName))

	if cfg.StartupFailure {
		logPrint("ERROR", "Failed to initialize server configuration or bind port.")
		os.Exit(cfg.CrashExitCode)
	}

	logPrint("INFO", "Profiler config ('bootstrap.json') load result: success=1, errorMessage=(null)")
	logPrint("INFO", "No CDN config file found at: cdn_config.json for dedicated server")
	logPrint("INFO", "Game mode: 1 Creative")
	logPrint("INFO", "Difficulty: 1 EASY")
	logPrint("WARN", "Content logging to console is disabled.  Enable it with content-log-console-output-enabled=true in server.properties")
	logPrint("INFO", " ")
	fmt.Println("#####################################################")
	fmt.Println("#                                                   #")
	fmt.Println("#               LOADING VANILLA WORLD               #")
	fmt.Println("#                                                   #")
	fmt.Println("#####################################################")

	if cfg.StartupDelayMs > 0 {
		time.Sleep(time.Duration(cfg.StartupDelayMs) * time.Millisecond)
	}

	logPrint("INFO", fmt.Sprintf("Opening level 'worlds/%s/db'", cfg.LevelName))
	logPrint("INFO", "Pack Stack - None")
	logPrint("INFO", "IPv4 supported, port: 19132: Used for gameplay and LAN discovery")
	logPrint("INFO", "IPv6 supported, port: 19133: Used for gameplay")
	logPrint("INFO", "Signed in to signaling service successfully")
	logPrint("INFO", "Waiting for Minecraft services...")

	if cfg.StartupDelayMs > 0 {
		time.Sleep(time.Duration(cfg.StartupDelayMs) * time.Millisecond)
	}

	if !cfg.NeverReady {
		logPrint("INFO", "Server started.")
		logPrint("INFO", "================ TELEMETRY MESSAGE ===================")
		logPrint("INFO", "Server Telemetry is currently not enabled. ")
		logPrint("INFO", "Enabling this telemetry helps us improve the game.")
		logPrint("INFO", " ")
		logPrint("INFO", "To enable this feature, add the line 'emit-server-telemetry=true'")
		logPrint("INFO", "to the server.properties file in the handheld/src-server directory")
		logPrint("INFO", "======================================================")
	}

	state := newServerState(cfg)

	if cfg.CrashAfterMs > 0 {
		go func(delayMs int, code int) {
			time.Sleep(time.Duration(delayMs) * time.Millisecond)
			logPrint("ERROR", "CRASH: Timed runtime failure triggered.")
			os.Exit(code)
		}(cfg.CrashAfterMs, cfg.CrashExitCode)
	}

	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		text := strings.TrimSpace(scanner.Text())
		if text == "" {
			continue
		}
		state.recordCommand(text)
		shouldExit, exitCode := state.processCommand(text)
		if shouldExit {
			os.Exit(exitCode)
		}
	}

	if err := scanner.Err(); err != nil {
		fmt.Fprintln(os.Stderr, "reading standard input:", err)
	}

	state.mu.Lock()
	stayAlive := state.ignoreStop
	state.mu.Unlock()
	if stayAlive {
		for {
			time.Sleep(10 * time.Second)
		}
	}
}

func (s *ServerState) processCommand(text string) (bool, int) {
	if text == "stop" {
		s.mu.Lock()
		ignore := s.ignoreStop
		delayMs := s.stopDelayMs
		exitCode := s.config.ExitCode
		s.mu.Unlock()

		if ignore {
			logPrint("WARN", "Stop command ignored by server configuration.")
			return false, 0
		}
		logPrint("INFO", "Server stop requested.")
		if delayMs > 0 {
			time.Sleep(time.Duration(delayMs) * time.Millisecond)
		}
		logPrint("INFO", "Stopping server...")
		fmt.Println("Quit correctly")
		return true, exitCode
	}

	if text == "save hold" {
		s.mu.Lock()
		defer s.mu.Unlock()
		if s.saveHoldFail {
			logPrint("ERROR", "Save hold failed: unable to lock level database.")
			return false, 0
		}
		s.saveHeld = true
		s.saveQueryCount = 0
		s.mutateLiveFileIfConfigured()
		logPrint("INFO", "Saving...")
		return false, 0
	}

	if text == "save query" {
		s.mu.Lock()
		defer s.mu.Unlock()
		if s.saveQueryFail {
			logPrint("ERROR", "Save query failed: backup state error.")
			return false, 0
		}
		if !s.saveHeld {
			logPrint("ERROR", "Save has not been held.")
			return false, 0
		}
		s.saveQueryCount++
		s.mutateLiveFileIfConfigured()
		required := s.saveReadyPolls
		if required < 1 {
			required = 1
		}
		if s.saveQueryCount < required {
			logPrint("INFO", "The save is in progress...")
			return false, 0
		}
		logPrint("INFO", "Data saved. Files are now ready to be copied.")
		fmt.Println(s.getSaveFileList())
		return false, 0
	}

	if text == "save resume" {
		s.mu.Lock()
		defer s.mu.Unlock()
		if s.saveResumeFail {
			logPrint("ERROR", "Save resume failed: no active save hold or internal error.")
			return false, 0
		}
		s.saveHeld = false
		s.saveQueryCount = 0
		logPrint("INFO", "Changes to the level are resumed.")
		return false, 0
	}

	if strings.HasPrefix(text, "__DUMMY__") {
		return s.handleDummyCommand(text)
	}

	// Echo raw command back
	fmt.Println(text)
	return false, 0
}

func logPrint(level, message string) {
	// Standard Bedrock log format: [YYYY-MM-DD HH:MM:SS:ms LEVEL] message
	now := time.Now()
	ts := now.Format("2006-01-02 15:04:05")
	ms := now.Format(".000")[1:]
	fmt.Printf("[%s:%s %s] %s\n", ts, ms, level, message)
}

func (s *ServerState) handleDummyCommand(text string) (bool, int) {
	trimmed := strings.TrimSpace(strings.TrimPrefix(text, "__DUMMY__"))
	if trimmed == "" {
		return false, 0
	}
	parts := strings.Fields(trimmed)
	cmd := parts[0]
	rest := strings.TrimSpace(strings.TrimPrefix(trimmed, cmd))

	switch cmd {
	case "CRASH":
		code := s.config.CrashExitCode
		if len(parts) >= 2 {
			if parsed, err := strconv.Atoi(parts[1]); err == nil {
				code = parsed
			}
		}
		logPrint("ERROR", "CRASH: Fatal runtime error encountered. Core dumped.")
		return true, code

	case "CRASH_AFTER":
		delayMs := 100
		code := s.config.CrashExitCode
		if len(parts) >= 2 {
			if parsed, err := strconv.Atoi(parts[1]); err == nil {
				delayMs = parsed
			}
		}
		if len(parts) >= 3 {
			if parsed, err := strconv.Atoi(parts[2]); err == nil {
				code = parsed
			}
		}
		go func(d, c int) {
			time.Sleep(time.Duration(d) * time.Millisecond)
			logPrint("ERROR", "CRASH: Scheduled runtime crash triggered.")
			os.Exit(c)
		}(delayMs, code)
		return false, 0

	case "PLAYER_JOIN":
		name, xuid, pfid := parsePlayerArgs(rest)
		logPrint("INFO", fmt.Sprintf("Player connected: %s, xuid: %s", name, xuid))
		logPrint("INFO", fmt.Sprintf("Player PartyIdUpdate:  pfid: %s, partyid: , isLeader: false", pfid))
		logPrint("INFO", fmt.Sprintf("Player Spawned: %s xuid: %s, pfid: %s", name, xuid, pfid))
		return false, 0

	case "PLAYER_LEAVE":
		name, xuid, pfid := parsePlayerArgs(rest)
		logPrint("INFO", fmt.Sprintf("Player disconnected: %s, xuid: %s, pfid: %s", name, xuid, pfid))
		return false, 0

	case "STDOUT_BURST":
		count := 100
		lineBytes := 80
		if len(parts) >= 2 {
			if parsed, err := strconv.Atoi(parts[1]); err == nil && parsed > 0 {
				count = parsed
			}
		}
		if len(parts) >= 3 {
			if parsed, err := strconv.Atoi(parts[2]); err == nil && parsed > 0 {
				lineBytes = parsed
			}
		}
		payload := strings.Repeat("X", lineBytes)
		for i := 0; i < count; i++ {
			logPrint("INFO", fmt.Sprintf("BURST %05d %s", i, payload))
		}
		return false, 0

	case "STDERR_BURST":
		count := 50
		lineBytes := 80
		if len(parts) >= 2 {
			if parsed, err := strconv.Atoi(parts[1]); err == nil && parsed > 0 {
				count = parsed
			}
		}
		if len(parts) >= 3 {
			if parsed, err := strconv.Atoi(parts[2]); err == nil && parsed > 0 {
				lineBytes = parsed
			}
		}
		payload := strings.Repeat("E", lineBytes)
		for i := 0; i < count; i++ {
			fmt.Fprintf(os.Stderr, "[STDERR BURST %05d] %s\n", i, payload)
		}
		return false, 0

	case "PARTIAL_LINE":
		fmt.Print(rest)
		return false, 0

	case "COMPLETE_LINE":
		fmt.Println(rest)
		return false, 0

	case "DUMP_COMMANDS":
		s.mu.Lock()
		cmds := strings.Join(s.receivedCommands, "|")
		s.mu.Unlock()
		logPrint("INFO", fmt.Sprintf("COMMANDS_RECORDED: %s", cmds))
		return false, 0

	case "SET_SAVE_POLLS":
		if len(parts) >= 2 {
			if parsed, err := strconv.Atoi(parts[1]); err == nil {
				s.mu.Lock()
				s.saveReadyPolls = parsed
				s.mu.Unlock()
			}
		}
		return false, 0

	case "SET_SAVE_FAIL":
		// __DUMMY__ SET_SAVE_FAIL <hold|query|resume> <true|false>
		if len(parts) >= 3 {
			target := strings.ToLower(parts[1])
			val := strings.ToLower(parts[2]) == "true" || parts[2] == "1"
			s.mu.Lock()
			switch target {
			case "hold":
				s.saveHoldFail = val
			case "query":
				s.saveQueryFail = val
			case "resume":
				s.saveResumeFail = val
			}
			s.mu.Unlock()
		}
		return false, 0

	case "SET_IGNORE_STOP":
		if len(parts) >= 2 {
			val := strings.ToLower(parts[1]) == "true" || parts[1] == "1"
			s.mu.Lock()
			s.ignoreStop = val
			s.mu.Unlock()
		}
		return false, 0

	case "MUTATE_FILE":
		if len(parts) >= 2 {
			targetPath := parts[1]
			content := "mutated-during-backup\n"
			if len(parts) >= 3 {
				content = strings.Join(parts[2:], " ") + "\n"
			}
			_ = os.MkdirAll(filepath.Dir(targetPath), 0755)
			f, err := os.OpenFile(targetPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
			if err == nil {
				_, _ = f.WriteString(content)
				_ = f.Close()
				logPrint("INFO", fmt.Sprintf("Mutated file: %s", targetPath))
			}
		}
		return false, 0
	}

	return false, 0
}
