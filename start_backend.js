// start_backend.js — cross-platform backend launcher
// Uses the local .venv on both Windows and Linux/macOS
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

const isWindows = os.platform() === 'win32';

const python = isWindows
  ? path.join('.venv', 'Scripts', 'python.exe')
  : path.join('.venv', 'bin', 'python');

const args = ['-m', 'uvicorn', 'main:app', '--reload', '--app-dir', 'backend'];

console.log(`[backend] Starting: ${python} ${args.join(' ')}`);

const proc = spawn(python, args, { stdio: 'inherit', shell: false });

proc.on('error', (err) => {
  console.error(`[backend] Failed to start: ${err.message}`);
  console.error(`[backend] Make sure you have run: ${isWindows ? '.venv\\Scripts\\python' : '.venv/bin/python'} -m pip install -r backend/requirements.txt`);
  process.exit(1);
});

proc.on('exit', (code) => process.exit(code ?? 0));
