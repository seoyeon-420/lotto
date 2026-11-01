const bookList = document.querySelector('#bookList');
const bookSearch = document.querySelector('#bookSearch');
const configTabs = document.querySelector('#configTabs');
const weightRows = document.querySelector('#weightRows');
const addSectionBtn = document.querySelector('#addSectionBtn');
const weightTotal = document.querySelector('#weightTotal');
const weightHelp = document.querySelector('#weightHelp');
const dateInput = document.querySelector('#dateInput');
const submitBtn = document.querySelector('#submitBtn');
const statusEl = document.querySelector('#status');
const resultsEl = document.querySelector('#results');
const tabList = document.querySelector('#tabs');
const songResults = document.querySelector('#songResults');
let selectedBook = null;
let books = [];
// 성가책 파일명과 웹페이지 표시 이름 연결
const BOOK_NAMES = {
  "childrenDB": "어린이미사",
};
let current = null;
let activePosition = '입당';
const positions = ['입당','봉헌','성체','파견'];
const availableSections = ['celebration','입당송','본기도','제1독서','제2독서','화답송','복음 환호송','복음','영성체송'];
const sectionLabel = s => s === 'celebration' ? '전례명' : s;
const configs = {
  '입당': [{section:'입당송',weight:100}],
  '봉헌': [{section:'본기도',weight:100}],
  '성체': [{section:'영성체송',weight:100}],
  '파견': [{section:'복음',weight:100}]
};
let activeConfigPosition = '입당';
function renderConfig() {
  configTabs.replaceChildren();
  for (const p of positions) {
    const b=el('button','config-tab'+(p===activeConfigPosition?' active':''),p);
    b.type='button';b.setAttribute('role','tab');b.setAttribute('aria-selected', String(p===activeConfigPosition));
    b.addEventListener('click',()=>{activeConfigPosition=p;renderConfig();});configTabs.append(b);
  }
  const rows=configs[activeConfigPosition];
  weightRows.replaceChildren();
  rows.forEach((row,i)=>{
    const wrapper=el('div','weight-row');
    const select=el('select','section-select');select.setAttribute('aria-label',`${activeConfigPosition} ${i+1}번째 전례문`);
    for(const section of availableSections){
      const opt=el('option','',sectionLabel(section));opt.value=section;
      opt.disabled=rows.some((r,j)=>j!==i && r.section===section);
      select.append(opt);
    }
    select.value=row.section;
    select.addEventListener('change',()=>{row.section=select.value;renderConfig();});
    const box=el('div','weight-input-box');
    const input=el('input','weight-input');input.type='number';input.min='0';input.max='100';input.step='1';input.value=row.weight;
    input.setAttribute('aria-label',`${activeConfigPosition} ${sectionLabel(row.section)} 비율`);
    input.addEventListener('input',()=>{row.weight=input.value===''?null:Number(input.value);updateWeightState();});
    box.append(input,el('span','','%'));
    wrapper.append(select,box);
    if(rows.length>1){
      const remove=el('button','remove-section','×');remove.type='button';remove.title='이 항목 삭제';remove.setAttribute('aria-label',`${i+1}번째 항목 삭제`);
      remove.addEventListener('click',()=>{rows.splice(i,1);renderConfig();});wrapper.append(remove);
    }
    weightRows.append(wrapper);
  });
  updateWeightState();
}
function updateWeightState(){
  const rows=configs[activeConfigPosition];
  const total=rows.reduce((n,r)=>n+(r.weight===null?0:r.weight),0);
  weightTotal.textContent=`${total}%`;
  const ok=rows.every(r=>Number.isInteger(r.weight)&&r.weight>=0&&r.weight<=100)&&total===100&&rows.some(r=>r.weight>0);
  weightTotal.classList.toggle('invalid',!ok);
  weightHelp.textContent=ok?'설정이 유효합니다.':'이 순서의 가중치 합계를 100%로 맞춰 주세요.';
  addSectionBtn.disabled=rows.length>=4;
  addSectionBtn.textContent=rows.length>=4?'전례문은 최대 4개까지 추가할 수 있습니다':'＋ 전례 추가하기';
}
function collectConfigs(){
  const output={};
  for(const position of positions){
    const rows=configs[position];
    const total=rows.reduce((n,r)=>n+(r.weight===null?0:r.weight),0);
    if(total!==100 || rows.some(r=>!Number.isInteger(r.weight)||r.weight<0||r.weight>100)||new Set(rows.map(r=>r.section)).size!==rows.length){
      throw new Error(`${position}의 전례문과 반영 비율을 확인해 주세요. 합계는 100%여야 합니다.`);
    }
    output[position]=Object.fromEntries(rows.filter(r=>r.weight>0).map(r=>[r.section,r.weight/100]));
  }
  return output;
}
addSectionBtn.addEventListener('click',()=>{
  const rows=configs[activeConfigPosition];if(rows.length>=4)return;
  const next=availableSections.find(s=>!rows.some(r=>r.section===s));
  if(next){rows.push({section:next,weight:0});renderConfig();}
});


function el(tag, cls, content) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (content !== undefined) node.textContent = String(content);
  return node;
}
function renderBooks(filter='') {
  bookList.replaceChildren();
  const options = books.map(n =>({value:n, label:BOOK_NAMES[n] || n}));
  for (const item of options.filter(o => o.label.toLowerCase().includes(filter.toLowerCase()))) {
    const b = el('button', 'book' + (selectedBook===item.value?' active':''));
    b.type='button'; b.dataset.book=item.value;
    b.append(el('span','book-icon','▣'),el('span','',item.label));
    b.addEventListener('click', () => {
    // 이미 선택된 성가책이면 아무 동작도 하지 않음
    if (selectedBook === item.value) return;
    selectedBook = item.value;
    renderBooks(bookSearch.value);
    // 새로운 성가책의 카테고리 목록 불러오기
    CategoryBrowser.setBook(selectedBook);
    // 이전 성가책의 추천 결과 초기화
    current = null;
    resultsEl.classList.add('hidden');
    statusEl.textContent = '';
    });
    bookList.append(b);
  }
}
async function loadBooks() {
  try {
    const r = await fetch('/api/books');
    if (!r.ok) {throw new Error('성가책 목록을 불러오지 못했습니다.');}
    const d = await r.json();
    books = d.books || [];
    // 첫 번째 성가책 자동 선택
    selectedBook = books.length > 0 ? books[0] : null;
  } catch (e) {books = [];
    selectedBook = null;
    console.error('성가책 목록 불러오기 실패:', e);
  }
  renderBooks();
  // 선택된 기본 성가책의 카테고리 불러오기
  CategoryBrowser.setBook(selectedBook);
}
function validDate(date) {
  if(!/^\d{8}$/.test(date)) return false;
  const year=+date.slice(0,4), month=+date.slice(4,6), day=+date.slice(6,8);
  const d=new Date(Date.UTC(year,month-1,day));
  return d.getUTCFullYear()===year && d.getUTCMonth()+1===month && d.getUTCDate()===day;
}
function renderResults() {
  if(!current) return;
  document.querySelector('#resultTitle').textContent = current.celebration || '매일미사 성가 추천';
  document.querySelector('#resultDate').textContent = current.date;
  document.querySelector('#resultNote').textContent = [current.note,current.book_filter_note].filter(Boolean).join(' ');
  tabList.replaceChildren();
  for(const pos of positions){
    const b=el('button','tab'+(pos===activePosition?' active':''),pos);
    b.type='button';b.setAttribute('role','tab');b.setAttribute('aria-selected',String(pos===activePosition));
    b.addEventListener('click',()=>{activePosition=pos;renderResults();});tabList.append(b);
  }
  songResults.replaceChildren();
  const group=current.results[activePosition]||{};
  const used=(group.used_sections||[]).map(s=>s==='celebration'?'전례명':s).join(' · ');
  songResults.append(el('div','used-sections',`검색 참조 항목: ${used || '정보 없음'}`));
  const songs=group.songs||[];
  if(!songs.length){songResults.append(el('p','result-note','해당 조건에서 표시할 검색 후보가 없습니다.'));return;}
  songs.forEach((s,i)=>{
    const card=el('article','song');
    card.append(el('h3','',`${i+1}. ${s.title||s.hymn_id||'성가'}`));
    card.append(el('div','meta',`성가 식별자: ${s.hymn_id||'-'} · 분류: ${s.category||'-'}`));
    const score=Number(s.final_score ?? s.similarity);
    if(Number.isFinite(score))card.append(el('div','meta score',`검색 점수: ${score.toFixed(4)}`));
    songResults.append(card);
  });
}
async function submit() {
  const date=dateInput.value.trim();
  if(!validDate(date)){statusEl.textContent='날짜를 YYYYMMDD 형식의 유효한 숫자 8자리로 입력해 주세요.';statusEl.className='status error';dateInput.focus();return;}
  let searchConfig;
  try{searchConfig=collectConfigs();}catch(e){statusEl.textContent=e.message;statusEl.className='status error';return;}
  submitBtn.disabled=true;submitBtn.textContent='검색 중...';
  statusEl.className='status'; statusEl.textContent='매일미사를 읽고 성가를 찾아보고 있어요 . . .(최대 5분 소요)';
  try{
    const resp=await fetch('/api/recommend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date,search_config:searchConfig,book:selectedBook})});
    const data=await resp.json();if(!resp.ok)throw new Error(data.error||'검색에 실패했습니다.');
    current=data;activePosition='입당';renderResults();resultsEl.classList.remove('hidden');
    statusEl.textContent='추천 검색이 완료되었습니다.';
    resultsEl.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){statusEl.textContent=e.message;statusEl.className='status error';}
  finally{submitBtn.disabled=false;submitBtn.textContent='추천받기';}
}
dateInput.addEventListener('input', () => {dateInput.value = dateInput.value.replace(/\D/g, '').slice(0, 8);});
bookSearch.addEventListener('input', () => {renderBooks(bookSearch.value);});
submitBtn.addEventListener('click', submit);
// 기존 전례문 설정 화면 초기화
renderConfig();
// 카테고리 탐색 기능 초기화
CategoryBrowser.init();
// 성가책 목록 불러오기
loadBooks();
