'use strict';
const {parseChatGPT}=require('./chatgpt');const{parseClaude}=require('./claude');const{parseGemini}=require('./gemini');const{parseDeepSeek}=require('./deepseek');
function parseImport({source,input,format}){switch(source){case'chatgpt':return parseChatGPT(input);case'claude':return parseClaude(input);case'gemini':return parseGemini(input,{format});case'deepseek':return parseDeepSeek(input,{format});default:throw Object.assign(new Error('IMPORT_SOURCE_UNSUPPORTED'),{code:'IMPORT_SOURCE_UNSUPPORTED'});}}
module.exports={parseImport};

// IMP-07（冻结导入攻击矩阵）：一条损坏的会话不得让整批导入失败。
//
// parseImport 对单条输入是「要么成功、要么抛」，这在批量导入里意味着用户一份
// 三年的存档只要有一条坏记录就全军覆没。这里补上批量语义：坏的进隔离区并保留
// 原因，好的照常返回。这是新增能力，不改 parseImport 既有行为。
function parseImportBatch({ source, inputs, format }) {
  if (!Array.isArray(inputs)) {
    throw Object.assign(new Error('IMPORT_BATCH_INPUTS_REQUIRED'), { code: 'IMPORT_BATCH_INPUTS_REQUIRED' });
  }
  const parsed = [];
  const quarantined = [];
  for (let index = 0; index < inputs.length; index += 1) {
    try {
      parsed.push({ index, conversation: parseImport({ source, input: inputs[index], format }) });
    } catch (error) {
      // 只记错误码与位置，绝不把原始内容抄进隔离记录——那是用户的私有聊天。
      quarantined.push({
        index,
        code: (error && error.code) || 'IMPORT_RECORD_INVALID',
      });
    }
  }
  return Object.freeze({ parsed, quarantined });
}

module.exports.parseImportBatch = parseImportBatch;
