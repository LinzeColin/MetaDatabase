'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {buildBusinessMatrix}=require('./business-matrix');
function writeStatusSnapshot({filePath,lines,version,generatedAt=new Date().toISOString()}){const payload={schema_version:1,product:'CyberBoss',version,generated_at:generatedAt,business_lines:buildBusinessMatrix(lines)};const dir=path.dirname(filePath);fs.mkdirSync(dir,{recursive:true,mode:0o750});const tmp=`${filePath}.${process.pid}.tmp`;fs.writeFileSync(tmp,`${JSON.stringify(payload,null,2)}\n`,{encoding:'utf8',mode:0o640});fs.renameSync(tmp,filePath);return payload;}
module.exports={writeStatusSnapshot};
