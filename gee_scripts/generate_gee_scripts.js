const fs = require('fs');
const path = require('path');

// Thư mục gốc của bộ script GEE (chính là gee_scripts/).
const rootDir = __dirname;
// Nơi chứa template (*.template.js).
const templatesDir = path.join(rootDir, 'templates');
// Nơi chứa file output đã inject config.
const outputDir = path.join(rootDir, 'generated');
// File config trung tâm.
const configPath = path.join(rootDir, 'config.gee.js');

const config = require(configPath);

// Deep merge object (source ghi đè target), dùng để ghép common + script-specific.
function deepMerge(target, source) {
  if (!source || typeof source !== 'object' || Array.isArray(source)) {
    return source;
  }

  const output = Array.isArray(target) ? [...target] : { ...target };

  Object.keys(source).forEach((key) => {
    const sourceValue = source[key];
    const targetValue = output[key];

    if (sourceValue && typeof sourceValue === 'object' && !Array.isArray(sourceValue)) {
      output[key] = deepMerge(targetValue && typeof targetValue === 'object' ? targetValue : {}, sourceValue);
    } else {
      output[key] = sourceValue;
    }
  });

  return output;
}

// Tìm vị trí khối `var CONFIG = {...};` trong một file JS.
// Trả về [startIndex, endIndex] để thay thế bằng placeholder khi tạo template.
function findConfigBounds(content) {
  const startToken = 'var CONFIG = {';
  const startIndex = content.indexOf(startToken);

  if (startIndex < 0) {
    throw new Error('Không tìm thấy khối "var CONFIG = {...}" trong source.');
  }

  const openBraceIndex = content.indexOf('{', startIndex);
  let depth = 0;
  let endBraceIndex = -1;

  for (let i = openBraceIndex; i < content.length; i += 1) {
    const char = content[i];

    if (char === '{') {
      depth += 1;
    } else if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        endBraceIndex = i;
        break;
      }
    }
  }

  if (endBraceIndex < 0) {
    throw new Error('Không xác định được điểm kết thúc khối CONFIG.');
  }

  const semicolonIndex = content.indexOf(';', endBraceIndex);
  if (semicolonIndex < 0) {
    throw new Error('Không tìm thấy dấu ";" kết thúc khối CONFIG.');
  }

  return {
    startIndex,
    endIndex: semicolonIndex + 1
  };
}

// Đảm bảo template tồn tại:
// - Nếu đã có, dùng luôn.
// - Nếu chưa có, tạo từ source bằng cách thay khối CONFIG thành placeholder.
function ensureTemplateFromSource(sourceName, templateName, placeholder) {
  const templatePath = path.join(templatesDir, templateName);
  if (fs.existsSync(templatePath)) {
    return templatePath;
  }

  const sourcePath = path.join(rootDir, sourceName);
  if (!fs.existsSync(sourcePath)) {
    throw new Error(`Không tìm thấy source file: ${sourcePath}`);
  }

  const sourceContent = fs.readFileSync(sourcePath, 'utf8');
  const bounds = findConfigBounds(sourceContent);

  const templateContent =
    sourceContent.slice(0, bounds.startIndex)
      + `var CONFIG = ${placeholder};`
      + sourceContent.slice(bounds.endIndex);

  fs.mkdirSync(templatesDir, { recursive: true });
  fs.writeFileSync(templatePath, templateContent, 'utf8');

  return templatePath;
}

// Render template bằng cách thay placeholder __CONFIG_X__ bằng JSON config thật.
function renderWithConfig(templatePath, placeholder, scriptConfig) {
  const template = fs.readFileSync(templatePath, 'utf8');

  if (!template.includes(placeholder)) {
    throw new Error(`Template thiếu placeholder ${placeholder}: ${templatePath}`);
  }

  const configLiteral = JSON.stringify(scriptConfig, null, 2);
  return template.replace(placeholder, configLiteral);
}

// Build config cuối cùng cho từng script:
// scriptConfig = deepMerge(common, scriptSpecific)
function buildScriptConfigs() {
  const common = config.common || {};

  return {
    script01: deepMerge(common, config.script01 || {}),
    script03: deepMerge(common, config.script03 || {})
  };
}

// Luồng chính:
// 1) Build config
// 2) Đảm bảo có template
// 3) Render output
// 4) Ghi file vào generated/
function generate() {
  const scriptConfigs = buildScriptConfigs();

  const template01 = ensureTemplateFromSource(
    '01_sentinel1_acquisition.js',
    '01_sentinel1_acquisition.template.js',
    '__CONFIG_01__'
  );

  const template03 = ensureTemplateFromSource(
    '03_optical_landslide.js',
    '03_optical_landslide.template.js',
    '__CONFIG_03__'
  );

  const out01 = renderWithConfig(template01, '__CONFIG_01__', scriptConfigs.script01);
  const out03 = renderWithConfig(template03, '__CONFIG_03__', scriptConfigs.script03);

  fs.mkdirSync(outputDir, { recursive: true });

  const out01Path = path.join(outputDir, '01_sentinel1_acquisition.js');
  const out03Path = path.join(outputDir, '03_optical_landslide.js');

  fs.writeFileSync(out01Path, out01, 'utf8');
  fs.writeFileSync(out03Path, out03, 'utf8');

  // Log danh sách file để người dùng biết đã tạo/tham chiếu những gì.
  console.log('✅ Generate thành công:');
  console.log(`- ${path.relative(rootDir, template01)}`);
  console.log(`- ${path.relative(rootDir, template03)}`);
  console.log(`- ${path.relative(rootDir, out01Path)}`);
  console.log(`- ${path.relative(rootDir, out03Path)}`);
}

// Chạy generator ngay khi execute file này bằng Node.js.
generate();
