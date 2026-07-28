'use strict';
const {parseChatGPT}=require('./chatgpt');const{parseClaude}=require('./claude');const{parseGemini}=require('./gemini');const{parseDeepSeek}=require('./deepseek');
function parseImport({source,input,format}){switch(source){case'chatgpt':return parseChatGPT(input);case'claude':return parseClaude(input);case'gemini':return parseGemini(input,{format});case'deepseek':return parseDeepSeek(input,{format});default:throw Object.assign(new Error('IMPORT_SOURCE_UNSUPPORTED'),{code:'IMPORT_SOURCE_UNSUPPORTED'});}}
module.exports={parseImport};
