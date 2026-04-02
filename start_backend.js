// start_backend.js — cross-platform backend launcher
// Works in local dev (.venv) and Docker (/opt/venv in PATH as "python")
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const isWindows = os.platform() === 'win32';
const isDev = process.env.NODE_ENV !== 'production';

// Resolve python: prefer local .venv (dev), fall back to system python (Docker/CI)
function resolvePython() {
  const localVenv = isWindows
    ? path.join('.venv', 'Scripts', 'python.exe')
    : path.join('.venv', 'bin', 'python');

  if (fs.existsSync(localVenv)) return localVenv;

  // Docker / system install — python is already on PATH via /opt/venv
  return isWindows ? 'python' : 'python3';
}

const python = resolvePython();

const args = [
  '-m', 'uvicorn', 'main:app',
  '--app-dir', 'backend',
  '--host', '0.0.0.0',
  '--port', process.env.BACKEND_PORT || '8000',
  ...(isDev ? ['--reload'] : []),
];

console.log(`[backend] python: ${python}`);
console.log(`[backend] Starting: ${args.join(' ')}`);

const proc = spawn(python, args, { stdio: 'inherit', shell: false });

proc.on('error', (err) => {
  console.error(`[backend] Failed to start: ${err.message}`);
  process.exit(1);
});

proc.on('exit', (code) => process.exit(code ?? 0));
