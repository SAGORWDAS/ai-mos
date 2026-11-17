const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const yaml = require('js-yaml');

test('validator permits cross-phase references and rejects invalid dependencies and cycles', () => {
  const scratch = path.resolve(__dirname, '..', '.tmp');
  fs.mkdirSync(scratch, { recursive: true });
  const root = fs.mkdtempSync(path.join(scratch, 'validator-'));
  try {
    fs.cpSync(path.join(__dirname, '..', 'spec'), path.join(root, 'spec'), { recursive: true });
    fs.mkdirSync(path.join(root, 'blueprint'));
    for (const file of ['validate.js', 'tasks.js']) {
      fs.copyFileSync(path.join(__dirname, file), path.join(root, 'blueprint', file));
    }
    const env = { ...process.env, NODE_PATH: path.join(__dirname, 'node_modules') };
    const run = () => spawnSync(process.execPath, [path.join(root, 'blueprint', 'validate.js')], { env, encoding: 'utf8' });
    const specPath = path.join(root, 'spec', 'ai-mos.spec.yaml');
    const original = fs.readFileSync(specPath, 'utf8');
    assert.equal(run().status, 0);
    let spec = yaml.load(original);
    spec.phases[0].tasks[0].depends = ['T-missing'];
    fs.writeFileSync(specPath, yaml.dump(spec));
    assert.equal(run().status, 1);
    spec = yaml.load(original);
    spec.phases[0].tasks[0].depends = [spec.phases[0].tasks[0].id];
    fs.writeFileSync(specPath, yaml.dump(spec));
    assert.equal(run().status, 1);
    fs.writeFileSync(specPath, original);
    fs.unlinkSync(path.join(root, 'spec', 'tasks', 'T-0.1.yaml'));
    assert.equal(run().status, 1);
  } finally {
    // Delete only the unique scratch directory created by this test.
    assert.equal(path.dirname(root), scratch);
    assert.ok(path.basename(root).startsWith('validator-'));
    fs.rmSync(root, { recursive: true, force: true });
  }
});
