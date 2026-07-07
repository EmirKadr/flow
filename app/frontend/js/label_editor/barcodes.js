// @ts-check
(function () {
  const CODE128_PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
  ];
  const QR_VERSIONS_L = {
    1: { data: 19, ecc: 7, blocks: 1 },
    2: { data: 34, ecc: 10, blocks: 1 },
    3: { data: 55, ecc: 15, blocks: 1 },
    4: { data: 80, ecc: 20, blocks: 1 },
    5: { data: 108, ecc: 26, blocks: 1 },
    6: { data: 136, ecc: 18, blocks: 2 },
  };
  const QR_ALIGN = { 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34] };
  const GF_EXP = [];
  const GF_LOG = Array(256).fill(0);

  let value = 1;
  for (let index = 0; index < 255; index += 1) {
    GF_EXP[index] = value;
    GF_LOG[value] = index;
    value <<= 1;
    if (value & 0x100) value ^= 0x11D;
  }
  for (let index = 255; index < 512; index += 1) GF_EXP[index] = GF_EXP[index - 255];

  function barcodeEscape(text) {
    return String(text ?? "").replace(/[&<>"']/g, (char) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
    ));
  }

  function gfMultiply(left, right) {
    if (!left || !right) return 0;
    return GF_EXP[GF_LOG[left] + GF_LOG[right]];
  }

  function rsGenerator(degree) {
    let result = [1];
    for (let index = 0; index < degree; index += 1) {
      const next = Array(result.length + 1).fill(0);
      result.forEach((coef, pos) => {
        next[pos] ^= coef;
        next[pos + 1] ^= gfMultiply(coef, GF_EXP[index]);
      });
      result = next;
    }
    return result;
  }

  function rsRemainder(data, degree) {
    const generator = rsGenerator(degree);
    const result = [...data, ...Array(degree).fill(0)];
    for (let index = 0; index < data.length; index += 1) {
      const coef = result[index];
      if (!coef) continue;
      generator.forEach((term, termIndex) => {
        result[index + termIndex] ^= gfMultiply(term, coef);
      });
    }
    return result.slice(data.length);
  }

  function bitsToCodewords(bits, count) {
    const data = [];
    for (let index = 0; index < count; index += 1) {
      let byte = 0;
      for (let bit = 0; bit < 8; bit += 1) byte = (byte << 1) | (bits[index * 8 + bit] || 0);
      data.push(byte);
    }
    return data;
  }

  function encodeQrData(text) {
    const bytes = Array.from(new TextEncoder().encode(String(text || " ")));
    const initialBitLength = 4 + 8 + bytes.length * 8;
    const version = Object.keys(QR_VERSIONS_L)
      .map(Number)
      .find((candidate) => initialBitLength <= QR_VERSIONS_L[candidate].data * 8);
    if (!version) throw new Error("QR-värdet är för långt. Korta texten eller dela upp etiketten.");

    const config = QR_VERSIONS_L[version];
    const bits = [];
    const appendBits = (number, length) => {
      for (let index = length - 1; index >= 0; index -= 1) bits.push((number >>> index) & 1);
    };
    appendBits(0x4, 4);
    appendBits(bytes.length, 8);
    bytes.forEach((byte) => appendBits(byte, 8));
    appendBits(0, Math.min(4, config.data * 8 - bits.length));
    while (bits.length % 8) bits.push(0);
    for (let padIndex = 0; bits.length < config.data * 8; padIndex += 1) {
      appendBits(padIndex % 2 ? 0x11 : 0xEC, 8);
    }
    const data = bitsToCodewords(bits, config.data);
    const blockLength = config.data / config.blocks;
    const blocks = Array.from({ length: config.blocks }, (_, index) => (
      data.slice(index * blockLength, (index + 1) * blockLength)
    ));
    const eccBlocks = blocks.map((block) => rsRemainder(block, config.ecc));
    const words = [];
    for (let pos = 0; pos < blockLength; pos += 1) blocks.forEach((block) => words.push(block[pos]));
    for (let pos = 0; pos < config.ecc; pos += 1) eccBlocks.forEach((block) => words.push(block[pos]));
    return { version, words };
  }

  function makeQrBase(version) {
    const size = version * 4 + 17;
    const matrix = Array.from({ length: size }, () => Array(size).fill(false));
    const reserved = Array.from({ length: size }, () => Array(size).fill(false));
    const set = (x, y, dark) => {
      if (x < 0 || y < 0 || x >= size || y >= size) return;
      matrix[y][x] = Boolean(dark);
      reserved[y][x] = true;
    };
    const finder = (left, top) => {
      for (let y = -1; y <= 7; y += 1) for (let x = -1; x <= 7; x += 1) {
        const inRing = x >= 0 && x <= 6 && y >= 0 && y <= 6;
        const dark = inRing && (x === 0 || x === 6 || y === 0 || y === 6 || (x >= 2 && x <= 4 && y >= 2 && y <= 4));
        set(left + x, top + y, dark);
      }
    };
    finder(0, 0);
    finder(size - 7, 0);
    finder(0, size - 7);
    for (let index = 8; index < size - 8; index += 1) {
      set(index, 6, index % 2 === 0);
      set(6, index, index % 2 === 0);
    }
    (QR_ALIGN[version] || []).forEach((cx) => (QR_ALIGN[version] || []).forEach((cy) => {
      if (reserved[cy]?.[cx]) return;
      for (let y = -2; y <= 2; y += 1) for (let x = -2; x <= 2; x += 1) {
        set(cx + x, cy + y, Math.max(Math.abs(x), Math.abs(y)) !== 1);
      }
    }));
    for (let index = 0; index <= 8; index += 1) {
      if (index !== 6) {
        set(8, index, false);
        set(index, 8, false);
      }
    }
    for (let index = 0; index < 8; index += 1) set(size - 1 - index, 8, false);
    for (let index = 8; index < 15; index += 1) set(8, size - 15 + index, false);
    set(8, size - 8, true);
    return { matrix, reserved, size };
  }

  function qrMask(mask, x, y) {
    const product = x * y;
    return [
      (x + y) % 2 === 0,
      y % 2 === 0,
      x % 3 === 0,
      (x + y) % 3 === 0,
      (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0,
      (product % 2) + (product % 3) === 0,
      ((product % 2) + (product % 3)) % 2 === 0,
      ((x + y) % 2 + (product % 3)) % 2 === 0,
    ][mask];
  }

  function formatBits(mask) {
    let data = (1 << 3) | mask;
    let bits = data << 10;
    for (let bit = 14; bit >= 10; bit -= 1) {
      if ((bits >>> bit) & 1) bits ^= 0x537 << (bit - 10);
    }
    return ((data << 10) | bits) ^ 0x5412;
  }

  function drawFormat(matrix, mask) {
    const size = matrix.length;
    const bits = formatBits(mask);
    const get = (index) => ((bits >>> index) & 1) === 1;
    for (let index = 0; index <= 5; index += 1) matrix[index][8] = get(index);
    matrix[7][8] = get(6);
    matrix[8][8] = get(7);
    matrix[8][7] = get(8);
    for (let index = 9; index < 15; index += 1) matrix[8][14 - index] = get(index);
    for (let index = 0; index < 8; index += 1) matrix[8][size - 1 - index] = get(index);
    for (let index = 8; index < 15; index += 1) matrix[size - 15 + index][8] = get(index);
    matrix[size - 8][8] = true;
  }

  function qrPenalty(matrix) {
    const size = matrix.length;
    let score = 0;
    const scoreLine = (line) => {
      let runColor = line[0];
      let run = 1;
      for (let index = 1; index <= line.length; index += 1) {
        if (line[index] === runColor) run += 1;
        else {
          if (run >= 5) score += 3 + run - 5;
          runColor = line[index];
          run = 1;
        }
      }
      const chars = line.map((cell) => (cell ? "1" : "0")).join("");
      const matches = chars.match(/10111010000|00001011101/g);
      if (matches) score += matches.length * 40;
    };
    for (let y = 0; y < size; y += 1) scoreLine(matrix[y]);
    for (let x = 0; x < size; x += 1) scoreLine(matrix.map((row) => row[x]));
    for (let y = 0; y < size - 1; y += 1) for (let x = 0; x < size - 1; x += 1) {
      if (matrix[y][x] === matrix[y][x + 1] && matrix[y][x] === matrix[y + 1][x] && matrix[y][x] === matrix[y + 1][x + 1]) score += 3;
    }
    const dark = matrix.flat().filter(Boolean).length;
    score += Math.floor(Math.abs(dark * 20 - size * size * 10) / (size * size)) * 10;
    return score;
  }

  function buildQrMatrix(text) {
    const { version, words } = encodeQrData(text);
    const base = makeQrBase(version);
    const dataBits = words.flatMap((word) => Array.from({ length: 8 }, (_, index) => (word >>> (7 - index)) & 1));
    let bitIndex = 0;
    let upward = true;
    for (let right = base.size - 1; right >= 1; right -= 2) {
      if (right === 6) right -= 1;
      for (let vert = 0; vert < base.size; vert += 1) {
        const y = upward ? base.size - 1 - vert : vert;
        for (let col = 0; col < 2; col += 1) {
          const x = right - col;
          if (base.reserved[y][x]) continue;
          base.matrix[y][x] = Boolean(dataBits[bitIndex]);
          bitIndex += 1;
        }
      }
      upward = !upward;
    }
    let best = null;
    for (let mask = 0; mask < 8; mask += 1) {
      const matrix = base.matrix.map((row) => row.slice());
      for (let y = 0; y < base.size; y += 1) for (let x = 0; x < base.size; x += 1) {
        if (!base.reserved[y][x] && qrMask(mask, x, y)) matrix[y][x] = !matrix[y][x];
      }
      drawFormat(matrix, mask);
      const penalty = qrPenalty(matrix);
      if (!best || penalty < best.penalty) best = { matrix, penalty };
    }
    return best.matrix;
  }

  function qrSvg(text, options = {}) {
    const matrix = buildQrMatrix(text);
    const quiet = Number(options.quiet ?? 4);
    const size = matrix.length + quiet * 2;
    const modules = [];
    matrix.forEach((row, y) => row.forEach((dark, x) => {
      if (dark) modules.push(`M${x + quiet} ${y + quiet}h1v1h-1z`);
    }));
    return `<svg viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="QR"><rect width="${size}" height="${size}" fill="#fff"/><path d="${modules.join("")}" fill="${barcodeEscape(options.color || "#111827")}"/></svg>`;
  }

  function code128Svg(text, options = {}) {
    const valueText = String(text || " ");
    if (!/^[ -~]+$/.test(valueText)) throw new Error("Code128 stödjer ASCII 32-126.");
    const codes = [104, ...Array.from(valueText).map((char) => char.charCodeAt(0) - 32)];
    const checksum = codes.reduce((sum, code, index) => sum + (index ? code * index : code), 0) % 103;
    codes.push(checksum, 106);
    const quiet = 10;
    let x = quiet;
    const bars = [];
    codes.forEach((code) => {
      Array.from(CODE128_PATTERNS[code]).forEach((widthChar, index) => {
        const width = Number(widthChar);
        if (index % 2 === 0) bars.push(`<rect x="${x}" y="4" width="${width}" height="42"/>`);
        x += width;
      });
    });
    const total = x + quiet;
    const label = options.showText === false ? "" : `<text x="${total / 2}" y="59" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#111827">${barcodeEscape(valueText)}</text>`;
    return `<svg viewBox="0 0 ${total} 64" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Code128"><rect width="${total}" height="64" fill="#fff"/><g fill="${barcodeEscape(options.color || "#111827")}">${bars.join("")}</g>${label}</svg>`;
  }

  window.FlowLabelBarcodes = { code128Svg, qrSvg };
})();
