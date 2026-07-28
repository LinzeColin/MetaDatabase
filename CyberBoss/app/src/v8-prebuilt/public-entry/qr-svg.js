'use strict';
const QRCode = require('../../../vendor/v8/qrcode-terminal/vendor/QRCode');
const QRErrorCorrectLevel = require('../../../vendor/v8/qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel');

function escapeXml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[ch]));
}

function renderQrSvg(value, { margin = 4, scale = 8, ariaLabel = '微信登录二维码' } = {}) {
  if (typeof value !== 'string' || !value.trim()) throw new TypeError('QR_VALUE_REQUIRED');
  if (!Number.isInteger(margin) || margin < 0 || margin > 16) throw new TypeError('QR_MARGIN_INVALID');
  if (!Number.isInteger(scale) || scale < 2 || scale > 32) throw new TypeError('QR_SCALE_INVALID');
  const qr = new QRCode(-1, QRErrorCorrectLevel.M);
  qr.addData(value);
  qr.make();
  const count = qr.getModuleCount();
  const full = count + margin * 2;
  const size = full * scale;
  const paths = [];
  for (let row = 0; row < count; row += 1) {
    for (let col = 0; col < count; col += 1) {
      if (qr.isDark(row, col)) paths.push(`M${(col + margin) * scale} ${(row + margin) * scale}h${scale}v${scale}h-${scale}z`);
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escapeXml(ariaLabel)}" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/><path d="${paths.join('')}" fill="#111827"/></svg>`;
}
function svgDataUri(svg) { return `data:image/svg+xml;base64,${Buffer.from(svg, 'utf8').toString('base64')}`; }
module.exports = { renderQrSvg, svgDataUri };
