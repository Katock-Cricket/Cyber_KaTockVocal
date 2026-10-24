package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func main() {
	base := strings.ToLower(filepath.Base(os.Args[0]))
	python := os.Getenv("KATOCK_FAKE_PY")
	script := os.Getenv("KATOCK_FAKE_AMD")
	switch {
	case strings.Contains(base, "separator"):
		script = os.Getenv("KATOCK_FAKE_SEP")
	case strings.Contains(base, "docker"):
		script = os.Getenv("KATOCK_FAKE_DOCKER")
	}
	if python == "" || script == "" {
		os.Stderr.WriteString("fake launcher missing script\n")
		os.Exit(2)
	}
	cmd := exec.Command(python, append([]string{script}, os.Args[1:]...)...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = os.Environ()
	err := cmd.Run()
	if err == nil {
		return
	}
	if exitErr, ok := err.(*exec.ExitError); ok {
		os.Exit(exitErr.ExitCode())
	}
	os.Stderr.WriteString(err.Error() + "\n")
	os.Exit(1)
}
