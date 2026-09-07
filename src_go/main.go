package main

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"time"
)

func main() {
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
	logPrint("INFO", "Level Name: Bedrock level")
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
	
	// Simulate delay for world loading
	time.Sleep(1 * time.Second)
	
	logPrint("INFO", "Opening level 'worlds/Bedrock level/db'")
	logPrint("INFO", "Accepting clients on [::]:19132")
	logPrint("INFO", "Pack Stack - None")
	logPrint("INFO", "Signed in to signaling service successfully")
	logPrint("INFO", "Waiting for Minecraft services...")
	
	// Simulate another delay
	time.Sleep(1 * time.Second)
	
	logPrint("INFO", "Server started.")
	logPrint("INFO", "================ TELEMETRY MESSAGE ===================")
	logPrint("INFO", "Server Telemetry is currently not enabled. ")
	logPrint("INFO", "Enabling this telemetry helps us improve the game.")
	logPrint("INFO", " ")
	logPrint("INFO", "To enable this feature, add the line 'emit-server-telemetry=true'")
	logPrint("INFO", "to the server.properties file in the handheld/src-server directory")
	logPrint("INFO", "======================================================")

	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		text := scanner.Text()
		text = strings.TrimSpace(text)
		
		if text == "stop" {
			logPrint("INFO", "Server stop requested.")
			logPrint("INFO", "Stopping server...")
			fmt.Println("Quit correctly")
			os.Exit(0)
		} else if strings.HasPrefix(text, "__DUMMY__") {
			handleDummyCommand(text)
		} else {
			// Echo raw command back
			fmt.Println(text)
		}
	}

	if err := scanner.Err(); err != nil {
		fmt.Fprintln(os.Stderr, "reading standard input:", err)
	}
}

func logPrint(level, message string) {
	// Standard Bedrock log format: [YYYY-MM-DD HH:MM:SS:ms LEVEL] message
	now := time.Now()
	// Go formatting: 2006 = YYYY, 01 = MM, 02 = DD, 15 = HH, 04 = MM, 05 = SS
	ts := now.Format("2006-01-02 15:04:05")
	ms := now.Format(".000")[1:] // get millisecond part
	fmt.Printf("[%s:%s %s] %s\n", ts, ms, level, message)
}

func handleDummyCommand(text string) {
	// Parse command
	parts := strings.Fields(text)
	if len(parts) < 2 {
		return
	}
	
	cmd := parts[1]
	
	if cmd == "PLAYER_JOIN" {
		player := "DummyPlayer"
		if len(parts) >= 3 {
			player = parts[2]
		}
		logPrint("INFO", fmt.Sprintf("Player connected: %s, xuid: 2535413537906883", player))
		logPrint("INFO", "Player PartyIdUpdate:  pfid: 94BDCFBEDC749828, partyid: , isLeader: false")
		logPrint("INFO", fmt.Sprintf("Player Spawned: %s xuid: 2535413537906883, pfid: 94BDCFBEDC749828", player))
	} else if cmd == "PLAYER_LEAVE" {
		player := "DummyPlayer"
		if len(parts) >= 3 {
			player = parts[2]
		}
		logPrint("INFO", fmt.Sprintf("Player disconnected: %s, xuid: 2535413537906883, pfid: 94BDCFBEDC749828", player))
	}
}
