import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPOSITORY_ROOT = resolve(ROOT, "..");
const CONTRACT_PATH = join(ROOT, "SOURCE_PROJECTION_CONTRACT.json");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: options.encoding ?? "utf8",
    env: options.env ?? process.env,
    input: options.input,
    maxBuffer: options.maxBuffer ?? 64 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, command + " " + args.join(" ") + " failed: " + String(result.stderr).trim());
  return result.stdout;
}

function runBinary(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: "buffer",
    env: options.env ?? process.env,
    maxBuffer: options.maxBuffer ?? 64 * 1024 * 1024,
  });
  if (result.error) throw result.error;
  assert.equal(result.status, 0, command + " " + args.join(" ") + " failed: " + String(result.stderr).trim());
  return result.stdout;
}

function trim(value) {
  return String(value).trim();
}

async function main() {
  const contract = JSON.parse(await readFile(CONTRACT_PATH, "utf8"));
  const { source, projection } = contract;
  const contentProjection = projection.content_projection;
  const sourceChannel = projection.source_channel;
  assert.equal(contract.contract_id, "PWB-S5-SOURCE-PROJECTION-001");
  assert.equal(source.repository, "MetaDatabase");
  assert.equal(source.project_path, "Personal-WorkBench");
  assert.match(source.commit, /^[0-9a-f]{40}$/);
  assert.match(source.root_tree, /^[0-9a-f]{40}$/);
  assert.match(source.project_tree, /^[0-9a-f]{40}$/);
  assert.equal(contentProjection.parent, null);
  assert.match(contentProjection.tree, /^[0-9a-f]{40}$/);
  assert.match(contentProjection.commit, /^[0-9a-f]{40}$/);
  assert.equal(typeof contentProjection.commit_message_subject, "string");
  assert(Array.isArray(contentProjection.commit_message_body_lines));
  assert.match(sourceChannel.parent, /^[0-9a-f]{40}$/);
  assert.match(sourceChannel.tree, /^[0-9a-f]{40}$/);
  assert.match(sourceChannel.commit, /^[0-9a-f]{40}$/);
  assert.equal(sourceChannel.push_mode, "NON_FORCE_FAST_FORWARD");
  assert.equal(sourceChannel.post_push_source_readback_required, true);

  const sourceCommit = trim(run("git", ["-C", REPOSITORY_ROOT, "rev-parse", source.commit + "^{commit}"]));
  const sourceRootTree = trim(run("git", ["-C", REPOSITORY_ROOT, "rev-parse", source.commit + "^{tree}"]));
  const sourceProjectTree = trim(run("git", ["-C", REPOSITORY_ROOT, "rev-parse", source.commit + ":" + source.project_path]));
  const sourceFileCount = Number(
    trim(run("git", ["-C", REPOSITORY_ROOT, "ls-tree", "-r", "--name-only", source.commit, "--", source.project_path]))
      .split("\n")
      .filter(Boolean).length,
  );

  assert.equal(sourceCommit, source.commit);
  assert.equal(sourceRootTree, source.root_tree);
  assert.equal(sourceProjectTree, source.project_tree);
  assert.equal(sourceFileCount, source.tracked_file_count);

  const temporaryRoot = await mkdtemp(join(tmpdir(), "pwb-source-projection-"));
  const projectRoot = join(temporaryRoot, source.project_path);
  try {
    await mkdir(projectRoot, { recursive: true });
    const archive = runBinary("git", ["-C", REPOSITORY_ROOT, "archive", source.commit + ":" + source.project_path]);
    run("tar", ["-x", "-C", projectRoot], { input: archive, encoding: "buffer" });

    run("git", ["-C", projectRoot, "init", "-q", "-b", projection.branch]);
    run("git", ["-C", projectRoot, "add", "-A"]);
    const projectionTree = trim(run("git", ["-C", projectRoot, "write-tree"]));
    assert.equal(projectionTree, source.project_tree);
    assert.equal(projectionTree, contentProjection.tree);

    const identityEnv = {
      ...process.env,
      GIT_AUTHOR_NAME: contentProjection.author_name,
      GIT_AUTHOR_EMAIL: contentProjection.author_email,
      GIT_AUTHOR_DATE: contentProjection.timestamp_utc,
      GIT_COMMITTER_NAME: contentProjection.author_name,
      GIT_COMMITTER_EMAIL: contentProjection.author_email,
      GIT_COMMITTER_DATE: contentProjection.timestamp_utc,
    };
    const projectionCommit = trim(run(
      "git",
      [
        "-C",
        projectRoot,
        "commit-tree",
        projectionTree,
        "-m",
        contentProjection.commit_message_subject,
        "-m",
        contentProjection.commit_message_body_lines.join("\n"),
      ],
      { env: identityEnv },
    ));
    const projectionTreeReadback = trim(run("git", ["-C", projectRoot, "rev-parse", projectionCommit + "^{tree}"]));
    const projectionFileCount = Number(trim(run("git", ["-C", projectRoot, "ls-files"])).split("\n").filter(Boolean).length);
    const parentProbe = spawnSync("git", ["-C", projectRoot, "rev-parse", projectionCommit + "^"], { encoding: "utf8" });

    assert.equal(projectionCommit, contentProjection.commit);
    assert.equal(projectionTreeReadback, source.project_tree);
    assert.equal(projectionFileCount, source.tracked_file_count);
    assert.notEqual(parentProbe.status, 0, "projection commit must have no parent");
    assert.equal(sourceChannel.tree, source.project_tree);

    console.log(
      JSON.stringify({
        status: "PASS_SOURCE_PROJECTION_CONTRACT",
        product_pass_claimed: false,
        remote_action_taken: false,
        source: {
          commit: sourceCommit,
          root_tree: sourceRootTree,
          project_tree: sourceProjectTree,
          tracked_file_count: sourceFileCount,
        },
        content_projection: {
          commit: projectionCommit,
          tree: projectionTreeReadback,
          tracked_file_count: projectionFileCount,
          parent: null,
        },
        source_channel: {
          commit: sourceChannel.commit,
          tree: sourceChannel.tree,
          parent: sourceChannel.parent,
          push_mode: sourceChannel.push_mode,
          post_push_source_readback_required: sourceChannel.post_push_source_readback_required,
        },
      }),
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
