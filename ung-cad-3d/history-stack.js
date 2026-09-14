function deepClone(s){return JSON.parse(JSON.stringify(s));}
function createHistory(initialState,maxSize=50){return{past:[],present:deepClone(initialState),future:[],maxSize};}
function pushState(h,newState){const past=[...h.past,h.present];if(past.length>h.maxSize)past.shift();return{past,present:deepClone(newState),future:[],maxSize:h.maxSize};}
function undo(h){if(!h.past.length)return h;const previous=h.past[h.past.length-1];return{past:h.past.slice(0,-1),present:previous,future:[h.present,...h.future],maxSize:h.maxSize};}
function redo(h){if(!h.future.length)return h;const next=h.future[0];return{past:[...h.past,h.present],present:next,future:h.future.slice(1),maxSize:h.maxSize};}
function canUndo(h){return h.past.length>0;} function canRedo(h){return h.future.length>0;}
window.HistoryStack={createHistory,pushState,undo,redo,canUndo,canRedo};
