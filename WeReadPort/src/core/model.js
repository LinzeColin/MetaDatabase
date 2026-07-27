/**
 * Canonical Reading Model (documentation typedefs; runtime uses serializable plain objects).
 *
 * @typedef {Object} NotebookSummary
 * @property {string} bookId
 * @property {string} title
 * @property {string} author
 * @property {string|undefined} coverUrl
 * @property {string|undefined} deepLink
 * @property {number} reviewCount
 * @property {number} highlightCount
 * @property {number} bookmarkCount
 * @property {number} totalNoteCount
 * @property {number|undefined} readingProgress
 * @property {number|undefined} sort
 *
 * @typedef {Object} CanonicalBook
 * @property {string} schemaVersion
 * @property {{provider:string,bookId:string,skillVersion:string}} source
 * @property {{id:string,title:string,author:string,translator:string,coverUrl:string,deepLink:string,intro:string,category:string,publisher:string,publishTime:string,isbn:string,wordCount:number|undefined,rating:number|undefined}} metadata
 * @property {{highlights:number,thoughtsAndReviews:number,officialHighlightCount:number,officialReviewCount:number,officialBookmarkCount:number}} counts
 * @property {{progress:number|undefined,readingTimeSeconds:number|undefined,updateTime:number|undefined}} progress
 * @property {Array<{uid:string,title:string,level:number,chapterIdx:number}>} chapters
 * @property {Array<Record<string,unknown>>} highlights
 * @property {Array<Record<string,unknown>>} thoughts
 * @property {number|undefined} sourceSnapshotAt
 * @property {string|undefined} sourceSnapshotAtIso
 * @property {string[]} warnings
 *
 * @typedef {Object} CanonicalSnapshot
 * @property {string} schemaVersion
 * @property {string} source
 * @property {string} sourceSkillVersion
 * @property {string} exportProfile
 * @property {CanonicalBook[]} books
 * @property {Array<{code:string,message:string,bookId?:string}>} failures
 * @property {Record<string,unknown>|undefined} readingStatistics
 */
export const MODEL_DOCUMENTATION_ONLY = true;
