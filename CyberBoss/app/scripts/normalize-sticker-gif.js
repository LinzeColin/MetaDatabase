#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const zlib = require("zlib");

const SIPS_PATH = "/usr/bin/sips";
const DEFAULT_SIZE = 240;
const MAX_SIZE = 1024;
const MAX_PNG_DIMENSION = 8192;
const PNG_SIGNATURE = Buffer.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
]);

function main() {
  const args = process.argv.slice(2);
  const inputPath = readFlag(args, "--input");
  const outputPath = readFlag(args, "--output");
  const size = Number.parseInt(readFlag(args, "--size") || String(DEFAULT_SIZE), 10);

  if (!inputPath || !outputPath) {
    throw new Error("Usage: normalize-sticker-gif.js --input <path> --output <path> [--size 240]");
  }
  const resolvedInputPath = path.resolve(inputPath);
  const resolvedOutputPath = path.resolve(outputPath);
  if (!fs.existsSync(resolvedInputPath)) {
    throw new Error(`Input file does not exist: ${resolvedInputPath}`);
  }
  fs.mkdirSync(path.dirname(resolvedOutputPath), { recursive: true });

  const input = fs.readFileSync(resolvedInputPath);
  if (input.subarray(0, 4).toString("ascii") === "GIF8") {
    fs.copyFileSync(resolvedInputPath, resolvedOutputPath);
    return;
  }

  const normalizedSize = (
    Number.isInteger(size) && size > 0 && size <= MAX_SIZE
  ) ? size : DEFAULT_SIZE;
  if (input.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)) {
    fs.writeFileSync(
      resolvedOutputPath,
      encodeStaticGif(resizePngToIndexed(input, normalizedSize))
    );
    return;
  }

  if (process.platform !== "darwin") {
    throw new Error(
      "Sticker GIF normalization accepts GIF and PNG on this platform; " +
      "other image formats require an approved converter."
    );
  }
  if (!fs.existsSync(SIPS_PATH)) {
    throw new Error(`Required tool missing: ${SIPS_PATH}`);
  }

  const result = spawnSync(SIPS_PATH, [
    "-s", "format", "gif",
    "-z", String(normalizedSize), String(normalizedSize),
    resolvedInputPath,
    "--out", resolvedOutputPath,
  ], {
    encoding: "utf8",
  });

  if (result.status !== 0) {
    const stderr = String(result.stderr || "").trim();
    const stdout = String(result.stdout || "").trim();
    throw new Error(`sips gif normalization failed: ${stderr || stdout || `exit ${result.status}`}`);
  }
  if (!fs.existsSync(resolvedOutputPath)) {
    throw new Error(`GIF normalization produced no output: ${resolvedOutputPath}`);
  }
}

function resizePngToIndexed(buffer, size) {
  const png = decodePng(buffer);
  const indexed = Buffer.alloc(size * size);
  for (let y = 0; y < size; y += 1) {
    const sourceY = Math.min(
      png.height - 1,
      Math.floor((y * png.height) / size)
    );
    for (let x = 0; x < size; x += 1) {
      const sourceX = Math.min(
        png.width - 1,
        Math.floor((x * png.width) / size)
      );
      const offset = (sourceY * png.width + sourceX) * 4;
      indexed[y * size + x] = paletteIndex(
        png.pixels[offset],
        png.pixels[offset + 1],
        png.pixels[offset + 2],
        png.pixels[offset + 3]
      );
    }
  }
  return { width: size, height: size, indexed };
}

function decodePng(buffer) {
  if (!Buffer.isBuffer(buffer) || !buffer.subarray(0, 8).equals(PNG_SIGNATURE)) {
    throw new Error("Invalid PNG signature.");
  }

  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = -1;
  let interlace = -1;
  let palette = null;
  let transparency = null;
  const idat = [];
  let offset = PNG_SIGNATURE.length;
  while (offset + 12 <= buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.subarray(offset + 4, offset + 8).toString("ascii");
    const dataStart = offset + 8;
    const dataEnd = dataStart + length;
    if (dataEnd + 4 > buffer.length) {
      throw new Error("Truncated PNG chunk.");
    }
    const data = buffer.subarray(dataStart, dataEnd);
    if (type === "IHDR") {
      if (length !== 13) {
        throw new Error("Invalid PNG IHDR.");
      }
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === "PLTE") {
      palette = Buffer.from(data);
    } else if (type === "tRNS") {
      transparency = Buffer.from(data);
    } else if (type === "IDAT") {
      idat.push(Buffer.from(data));
    } else if (type === "IEND") {
      break;
    }
    offset = dataEnd + 4;
  }

  if (
    width < 1 || height < 1 ||
    width > MAX_PNG_DIMENSION || height > MAX_PNG_DIMENSION
  ) {
    throw new Error("PNG dimensions are outside the accepted boundary.");
  }
  if (bitDepth !== 8 || interlace !== 0) {
    throw new Error("Only non-interlaced 8-bit PNG inputs are supported.");
  }
  const bytesPerPixel = new Map([
    [0, 1],
    [2, 3],
    [3, 1],
    [4, 2],
    [6, 4],
  ]).get(colorType);
  if (!bytesPerPixel || !idat.length) {
    throw new Error("Unsupported or incomplete PNG input.");
  }
  if (colorType === 3 && (!palette || palette.length % 3 !== 0)) {
    throw new Error("Indexed PNG input is missing a valid palette.");
  }

  const rowBytes = width * bytesPerPixel;
  const expectedBytes = (rowBytes + 1) * height;
  const inflated = zlib.inflateSync(Buffer.concat(idat), {
    maxOutputLength: expectedBytes,
  });
  if (inflated.length !== expectedBytes) {
    throw new Error("PNG pixel payload length mismatch.");
  }

  const raw = Buffer.alloc(rowBytes * height);
  let inputOffset = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = inflated[inputOffset];
    inputOffset += 1;
    const rowOffset = y * rowBytes;
    const previousOffset = (y - 1) * rowBytes;
    for (let x = 0; x < rowBytes; x += 1) {
      const encoded = inflated[inputOffset + x];
      const left = x >= bytesPerPixel ? raw[rowOffset + x - bytesPerPixel] : 0;
      const up = y > 0 ? raw[previousOffset + x] : 0;
      const upLeft = y > 0 && x >= bytesPerPixel
        ? raw[previousOffset + x - bytesPerPixel]
        : 0;
      let predictor = 0;
      if (filter === 1) {
        predictor = left;
      } else if (filter === 2) {
        predictor = up;
      } else if (filter === 3) {
        predictor = Math.floor((left + up) / 2);
      } else if (filter === 4) {
        predictor = paeth(left, up, upLeft);
      } else if (filter !== 0) {
        throw new Error(`Unsupported PNG filter: ${filter}`);
      }
      raw[rowOffset + x] = (encoded + predictor) & 0xff;
    }
    inputOffset += rowBytes;
  }

  const pixels = Buffer.alloc(width * height * 4);
  for (let index = 0; index < width * height; index += 1) {
    const source = index * bytesPerPixel;
    const target = index * 4;
    if (colorType === 0) {
      pixels[target] = raw[source];
      pixels[target + 1] = raw[source];
      pixels[target + 2] = raw[source];
      pixels[target + 3] = 255;
    } else if (colorType === 2) {
      pixels[target] = raw[source];
      pixels[target + 1] = raw[source + 1];
      pixels[target + 2] = raw[source + 2];
      pixels[target + 3] = 255;
    } else if (colorType === 3) {
      const paletteIndexValue = raw[source];
      const paletteOffset = paletteIndexValue * 3;
      if (paletteOffset + 2 >= palette.length) {
        throw new Error("Indexed PNG references an invalid palette entry.");
      }
      pixels[target] = palette[paletteOffset];
      pixels[target + 1] = palette[paletteOffset + 1];
      pixels[target + 2] = palette[paletteOffset + 2];
      pixels[target + 3] = transparency?.[paletteIndexValue] ?? 255;
    } else if (colorType === 4) {
      pixels[target] = raw[source];
      pixels[target + 1] = raw[source];
      pixels[target + 2] = raw[source];
      pixels[target + 3] = raw[source + 1];
    } else {
      pixels[target] = raw[source];
      pixels[target + 1] = raw[source + 1];
      pixels[target + 2] = raw[source + 2];
      pixels[target + 3] = raw[source + 3];
    }
  }
  return { width, height, pixels };
}

function paeth(left, up, upLeft) {
  const estimate = left + up - upLeft;
  const leftDistance = Math.abs(estimate - left);
  const upDistance = Math.abs(estimate - up);
  const diagonalDistance = Math.abs(estimate - upLeft);
  if (leftDistance <= upDistance && leftDistance <= diagonalDistance) {
    return left;
  }
  return upDistance <= diagonalDistance ? up : upLeft;
}

function paletteIndex(red, green, blue, alpha) {
  if (alpha < 128) {
    return 0;
  }
  const r = Math.round((red * 5) / 255);
  const g = Math.round((green * 6) / 255);
  const b = Math.round((blue * 5) / 255);
  return 1 + r * 42 + g * 6 + b;
}

function encodeStaticGif({ width, height, indexed }) {
  const header = Buffer.from("GIF89a", "ascii");
  const descriptor = Buffer.alloc(7);
  descriptor.writeUInt16LE(width, 0);
  descriptor.writeUInt16LE(height, 2);
  descriptor[4] = 0xf7;
  descriptor[5] = 0;
  descriptor[6] = 0;

  const palette = Buffer.alloc(256 * 3);
  for (let r = 0; r < 6; r += 1) {
    for (let g = 0; g < 7; g += 1) {
      for (let b = 0; b < 6; b += 1) {
        const index = 1 + r * 42 + g * 6 + b;
        palette[index * 3] = Math.round((r * 255) / 5);
        palette[index * 3 + 1] = Math.round((g * 255) / 6);
        palette[index * 3 + 2] = Math.round((b * 255) / 5);
      }
    }
  }

  const control = Buffer.from([
    0x21, 0xf9, 0x04, 0x01, 0x00, 0x00, 0x00, 0x00,
  ]);
  const imageDescriptor = Buffer.alloc(10);
  imageDescriptor[0] = 0x2c;
  imageDescriptor.writeUInt16LE(width, 5);
  imageDescriptor.writeUInt16LE(height, 7);
  imageDescriptor[9] = 0;

  const codes = [];
  for (const value of indexed) {
    codes.push(256, value);
  }
  codes.push(257);
  const compressed = packNineBitCodes(codes);
  const blocks = [];
  for (let offset = 0; offset < compressed.length; offset += 255) {
    const block = compressed.subarray(offset, offset + 255);
    blocks.push(Buffer.from([block.length]), block);
  }
  return Buffer.concat([
    header,
    descriptor,
    palette,
    control,
    imageDescriptor,
    Buffer.from([8]),
    ...blocks,
    Buffer.from([0, 0x3b]),
  ]);
}

function packNineBitCodes(codes) {
  const output = [];
  let accumulator = 0;
  let bitCount = 0;
  for (const code of codes) {
    accumulator |= code << bitCount;
    bitCount += 9;
    while (bitCount >= 8) {
      output.push(accumulator & 0xff);
      accumulator >>>= 8;
      bitCount -= 8;
    }
  }
  if (bitCount > 0) {
    output.push(accumulator & 0xff);
  }
  return Buffer.from(output);
}

function readFlag(args, flag) {
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === flag) {
      return String(args[index + 1] || "").trim();
    }
  }
  return "";
}

try {
  main();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error || "unknown error");
  console.error(message);
  process.exit(1);
}
