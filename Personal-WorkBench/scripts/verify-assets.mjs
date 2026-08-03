import { createHash } from "node:crypto";
import { access, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const evidencePath = join(root, "13_evidence", "asset_manifest.json");
const taskpackRoot = process.env.TASKPACK_ROOT;
const record = process.argv.includes("--record");
const publicDeploy = process.argv.includes("--public-deploy");

const privateCrops = {
  "nav_anniversary_reference_crop.png": "f6802b751950359cdb81589012053fabcfb7bbbdb906e954bebae62a2c446abf",
  "nav_desktop_reference_crop.png": "2fc5f7daff5ca206017446b7995db239ff9364718268886eb11ae60e4dc50122",
  "nav_diary_reference_crop.png": "29a04c737bc88688f369ada74b1140a02e02a02022e2bab358f20b56ab213513",
  "nav_fatloss_reference_crop.png": "588849f23efc690a73a65ff72134e63e5eda14933fea059c69311c00824279f2",
  "nav_ledger_reference_crop.png": "10bba976238bfcd84981cdad766118c5201d0ce9ce5b73d28f452aab64a492fe",
  "nav_period_reference_crop.png": "047769edaa80fa2d517a8ae5c121048167a7daf6dbe352d466103e330d54998e",
  "nav_savings_reference_crop.png": "560fdb8901970c0bd3ed9fbb9afa1ed3631ae12d61c8793ae446286774063af4",
  "nav_schedule_reference_crop.png": "3381fb8dfce5558dd82011696822530c084470fe6ac1f535e726e9799f9741ec",
  "nav_todo_reference_crop.png": "76088fd73c132edf9343418c0e822a5fd97b0bb1f67a36ab9bef3c4a6a35b036",
  "welcome_hello_kitty_reference_crop.png": "7859519c39b51812592e99339a8b7d80317ec26d59b3a68981c2d0f9bbf6efda",
};

const runtimeAssets = {
  "app-icon-192.png": "aa8080339dcdc5631752dd63de24ba39ff1f18478f63649df1b9dee17c8c3a01",
  "app-icon-512.png": "604eee1ff367f9f49a35954d9bc0ac0de51f2dd21093ccd504945be7da2cce1b",
  "asset-contact-sheet.png": "bb283969c3b85a153461421f2ecf9603714a917ef84f23bdd338e9c7b4d82ccc",
  "fatloss_title.png": "b9dc0b9fef51a8e99a38583c4dc129c1d9df6ea93bcac8eb01bea159630dbbde",
  "food_camera.png": "5d075ded0db38c20044bb368b8d7737c64049b30fdb6244e360b3fc015a73ee1",
  "food_title.png": "7875c3e353dcf51a1dd02697ed7aa9dacd05ad1aa7ae6665f72133104dba16b7",
  "habit_early.png": "49c2d7f6ace275844cbd520b357cd6d454346c6b61ac058d88a85ca1d36da66f",
  "habit_read.png": "61f02ecfca44a27e210996fad82ce524ad25d6459505302f13f1865fbdbdd6e2",
  "habit_sleep.png": "e9430c06fb95143031d675650b80f66ed3ed4b1c4194ce73f86c06f4fe064fd2",
  "habit_sport.png": "52861cb57ef561a3071bdb8f8cd47b8783a4cf08f179d45fee4417e8c99f0457",
  "habit_water.png": "a3f45109906a23fd371eea680914e4bd721a9c09302eee9f63b64155390930c0",
  "ledger_title.png": "3f1c4682b4ce7d8e3b8dc9fc7fb650a59194de2bd23c05bbb41a23f26babde11",
  "nav_anniversary.png": "f03c582327c6aef92cfc8355b93bbed699a87053ae0c3ca0ec4eb1d6d0aed0e2",
  "nav_desktop.png": "37a82983ba88b0dbe62b90a37e85144c7d904c744bab279d652758bccfef6e85",
  "nav_diary.png": "99df01477ad324981e4eb6278df2ac3625ccaef9399da685f726f9b57f3c995b",
  "nav_fatloss.png": "cb601d73b6f5aa2b56d5911125de7236a1ba7e51fe6e314605f47f8dc1635f8b",
  "nav_ledger.png": "67d9b4adf2453c833c37abfbbf668ed52d2fe5fda6ebf79abb5a3ed7e5b550ae",
  "nav_period.png": "2c9bbf828cdfe55aacf8819a1d3d126953ee08d8fea52f6defdc898f5e019f5b",
  "nav_savings.png": "ca9c9017e24775846f81aff0db1c8ae09146a97e4a52fc8247a9311894e20a84",
  "nav_schedule.png": "c485132b54afb526d03de00e0903259b71c2e76c16ae1604b6f861dd2a2f4422",
  "nav_todo.png": "fc5ef0982ba7aef56ee9fffebec3b762f031554bb1e176e04e901366688626dd",
  "period_title.png": "c55a80717ee3a25dee23d2d123d34f1f4e44d6d847e38e8dee050ba894e75c9c",
  "tab_exercise.png": "e5008a47c4ab0c17c8aac8983b308cea17d21cb025640800cad4133a22eea9f0",
  "tab_food.png": "c7ba2bc9008ad4d7db446760e3e34f3f23f6c12c52e0c65ce175a64fdd285829",
  "tab_weight.png": "83de11ce15b00eeb25eb3ed712428e2df65803baa07ea40e925f82b3bf8af23d",
  "welcome_bow.png": "3c910dae62a0f46f3691f6396e23dad778b572f9ab2f33889904b00482bd4052",
  "welcome_hello_kitty.png": "cc15bff0a9de261435360807e0186d57f145e8467b0efbc04d3239237ddcb10f",
};

const visualTruth = [
  ["02_visual/references/01_欢迎页_视觉真值.png", "ddd17d4c843908390dcc440a5dddaa70a86b5e93b70040eac687a3c3ed42a79f"],
  ["02_visual/references/02_桌面页_视觉真值.png", "8f28f8c7f5356b3458ee5ce8a4bd4f2b8b4d6eba0404833bbfb251b5a387b3e2"],
  ["02_visual/references/03_记账页_视觉真值.png", "139c9efaa8d9f89ebed9aaf39c213bd56161e6a7d118316bcc066d0e304f1221"],
  ["02_visual/references/04_减脂饮食页_视觉真值.png", "2ae8dadb4cd8df8d07fa700a84331f9b9af31fad8f4944317532868ed77804b3"],
  ["02_visual/references/05_经期记录页_视觉真值.png", "070688753b86b19a7be620ae077e0a8ee7e655862aec8815dadb8f0f9b857537"],
];

const masks = [
  ["02_visual/masks/01_欢迎页_视觉真值_mask.png", "e3d24258d69b6f8a9f6fd60e36834cc69a57159a0fb5b750762d7a87883759d4"],
  ["02_visual/masks/02_桌面页_视觉真值_mask.png", "05250c41c2af61f0f53ce16255e3ce254365c927763636a43594cae58f4a5838"],
  ["02_visual/masks/03_记账页_视觉真值_mask.png", "93b7d1d3de8c84d6a5a6e5fbeea26cd08260b57611eb1bfdc3f28ae27b6ab643"],
  ["02_visual/masks/04_减脂饮食页_视觉真值_mask.png", "e1a3715f09793d8ed1b83662ab6838007002f49b9837fee2ebdf96e1d1febaef"],
  ["02_visual/masks/05_经期记录页_视觉真值_mask.png", "b283398d08b865494e4e1340e0c1c83079fa416808ed7ae4871db450db590750"],
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

function localEntries() {
  const crops = Object.entries(privateCrops).map(([name, sha256]) => ({
    path: `public/private-reference-assets/${name}`,
    source: `02_visual/private_reference_assets/${name}`,
    sha256,
    kind: "cropped_hello_kitty_private_reference",
  }));
  const runtime = Object.entries(runtimeAssets).map(([name, sha256]) => ({
    path: `public/private-reference-assets/runtime/${name}`,
    source: `05_prebuild/starter-kit/public/assets/images/${name}`,
    sha256,
    kind: "runtime_hello_kitty_or_reference_derived_asset",
  }));
  return [...crops, ...runtime].map((entry) => ({
    ...entry,
    source_description: "用户提供视觉真值或其受控衍生素材",
    rights_status: "OWNER_DECLARED_PRIVATE_VALIDATION_ALLOWED",
    allowed_use: "private Saved Candidate, layout calibration and visual diff only",
    public_deploy: "REQUIRES_FINAL_AUTHORIZED_ASSET_RECORD",
    first_party_license_included: false,
  }));
}

function report() {
  return {
    schema_version: "3.0.0",
    task_id: "S1-T1",
    status: "PRIVATE_CANDIDATE_PASS_PUBLIC_DEPLOY_BLOCKED",
    generated_at: new Date().toISOString(),
    asset_count: 42,
    visual_truth_inputs: visualTruth.map(([path, sha256]) => ({
      path,
      sha256,
      kind: "user_provided_visual_truth_screenshot",
      rights_status: "OWNER_DECLARED_REFERENCE_AND_PRIVATE_VALIDATION_ALLOWED",
      allowed_use: "private Saved Candidate, visual truth and diff",
    })),
    visual_masks: masks.map(([path, sha256]) => ({ path, sha256, compare_rule: "white=ignore, black=compare" })),
    private_candidate_assets: localEntries(),
    public_release_policy: {
      owner_declaration: "OWNER_APPROVAL.json",
      current_state: "BLOCKED_ASSET_RIGHTS",
      required_before_public_deploy: "final authorized original assets + rights record + same-container replacement",
      replacement_rule: "不得改变容器、裁切框、尺寸、位置、页面结构或 reference anchors",
      first_party_license_scope: "不包含 Hello Kitty、参考截图或衍生角色素材",
    },
  };
}

async function verifyTaskpackInputs() {
  if (!taskpackRoot) return false;
  for (const [path, expected] of [...visualTruth, ...masks]) {
    assert(await sha256(join(taskpackRoot, path)) === expected, `task pack hash mismatch: ${path}`);
  }
  return true;
}

async function main() {
  const expected = localEntries();
  for (const entry of expected) {
    const localPath = join(root, entry.path);
    await access(localPath);
    assert(await sha256(localPath) === entry.sha256, `private candidate asset hash mismatch: ${entry.path}`);
  }

  const taskpackInputsVerified = await verifyTaskpackInputs();
  const nextReport = report();
  if (record) await writeFile(evidencePath, `${JSON.stringify(nextReport, null, 2)}\n`, "utf8");

  let manifest = nextReport;
  try {
    manifest = JSON.parse(await readFile(evidencePath, "utf8"));
  } catch {
    if (!record) throw new Error("asset manifest missing; run npm run verify:assets -- --record after S1 asset intake");
  }
  assert(manifest.status === "PRIVATE_CANDIDATE_PASS_PUBLIC_DEPLOY_BLOCKED", "asset manifest must preserve the public asset-rights block");
  assert(manifest.private_candidate_assets?.length === 37, "asset manifest must account for all 37 private candidate assets");

  if (publicDeploy) {
    throw new Error("BLOCKED_ASSET_RIGHTS: final authorized Hello Kitty originals and a rights record are absent; public Deploy is forbidden");
  }

  console.log(JSON.stringify({
    status: "PASS_PRIVATE_CANDIDATE_PUBLIC_DEPLOY_BLOCKED",
    asset_count: expected.length + visualTruth.length,
    masks_verified: masks.length,
    taskpack_inputs_verified: taskpackInputsVerified,
    evidence: "13_evidence/asset_manifest.json",
  }));
}

await main();
