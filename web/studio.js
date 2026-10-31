import { app } from '../../scripts/app.js';
import { api } from '../../scripts/api.js';

const el=(tag,cls='',text='')=>{const x=document.createElement(tag);x.className=cls;x.textContent=text;return x;};
const endpoint=kind=>`/moss-card/library/${kind}`;
const thumb=(kind,id)=>api.apiURL(`${endpoint(kind)}/${encodeURIComponent(id)}/thumbnail`);
async function request(path,options){const r=await api.fetchApi(path,options);const data=await r.json();if(!r.ok)throw new Error(data.error||'Library request failed');return data;}

function editAsset(kind,entry,onSaved){
    const dialog=el('dialog','moss-studio-editor');dialog.setAttribute('aria-label',entry?'Edit library item':'Add library item');
    const form=el('form');form.method='dialog';
    form.append(el('h2','',`${entry?'Edit':'Add'} ${kind==='faces'?'face':'outfit'}`));
    const image=el('img');image.className='moss-studio-upload-preview';
    const file=el('input');file.type='file';file.accept='image/png,image/jpeg,image/webp';file.setAttribute('aria-label','Reference image');
    let objectURL;
    file.onchange=()=>{if(objectURL)URL.revokeObjectURL(objectURL);if(file.files[0])image.src=objectURL=URL.createObjectURL(file.files[0]);};
    if(entry){image.src=thumb(kind,entry.id);}else{form.append(file);}
    form.append(image);
    const fields={};
    for(const [key,label,multiline,help]of[
        ['label','Name',false,'A short name you can recognize'],
        ['tags','Tags',false,'Separate tags with commas'],
        ['description',kind==='faces'?'Face details':'Shared garment identity',true,kind==='faces'?'Face shape, eyes, nose and lips only. Use separate fields for hair and expression.':'Garments, colors, materials, cut, lengths and shoes shared by both views. Put visible-side details below.'],
        ...(kind==='faces'?[['hair_description','Hairstyle',true,'Length, texture, bangs and part. Put color in Hair color.'],['hair_color','Hair color',false,'For example: dark brown'],['expression_description','Expression',true,'Smile intensity, mouth closed or parted, and whether teeth are visible']]:[
            ['front_details','Front-only details',true,'Visible buttons, lacing, chest prints or other details belonging to the front.'],
            ['back_details','Back-only details',true,'Known rear details only. Leave blank when the back design is unknown.'],
            ['portrait_description','Portrait clothing',true,'Neckline, shoulders and upper chest only. No skirt, waist, legs, shoes or bags. Put head and neck accessories here.']])
    ]){
        const labelEl=el('label','',label);const input=el(multiline?'textarea':'input');input.setAttribute('aria-label',label);input.placeholder=help;input.value=Array.isArray(entry?.[key])?entry[key].join(', '):(entry?.[key]||'');input.required=['label','description','portrait_description'].includes(key);input.maxLength=key==='label'?120:key==='tags'?1200:6000;labelEl.append(input);form.append(labelEl);fields[key]=input;
    }
    const asymmetricRows=[];
    if(kind==='outfits'){
        const section=el('section','moss-studio-asymmetries');section.append(el('h3','','Asymmetric features'));
        section.append(el('p','','Use the wearer’s own left/right. Choose which views can see each pocket, slit, strap, ornament or carried item.'));
        const rows=el('div');section.append(rows);
        const addFeature=value=>{const row=el('div','moss-studio-feature');const description=el('input');description.setAttribute('aria-label','Feature description');description.placeholder='Feature, without direction words';description.value=value?.description||'';description.maxLength=1000;
            const side=el('select');side.setAttribute('aria-label','Wearer side');for(const[v,label]of[['left','Wearer left'],['right','Wearer right'],['center','Centerline'],['both','Both sides']]){const option=el('option','',label);option.value=v;side.append(option);}side.value=value?.side||'left';
            const visible=el('select');visible.setAttribute('aria-label','Visible in');for(const[v,label]of[['both','Front and back'],['front','Front only'],['back','Back only']]){const option=el('option','',label);option.value=v;visible.append(option);}visible.value=value?.visible_in||'both';
            const remove=el('button','','Remove feature');remove.type='button';const record={description,side,visible};asymmetricRows.push(record);remove.onclick=()=>{asymmetricRows.splice(asymmetricRows.indexOf(record),1);row.remove();};row.append(description,side,visible,remove);rows.append(row);};
        for(const value of entry?.asymmetries||entry?.outfit_spec?.asymmetries||[])addFeature(value);
        const add=el('button','','Add asymmetric feature');add.type='button';add.onclick=()=>{if(asymmetricRows.length<24)addFeature();};section.append(add);form.append(section);
    }
    const error=el('p','moss-studio-error');error.setAttribute('role','status');
    const actions=el('div','moss-studio-actions');const cancel=el('button','','Cancel');cancel.type='button';cancel.onclick=()=>dialog.close();const save=el('button','','Save to my library');save.type='submit';actions.append(cancel,save);form.append(error,actions);
    form.onsubmit=async event=>{event.preventDefault();save.disabled=true;error.textContent='Saving…';try{
        const data=Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,input.value]));let saved;
        if(kind==='outfits')data.asymmetries=asymmetricRows.map(x=>({description:x.description.value,side:x.side.value,visible_in:x.visible.value}));
        if(entry){saved=await request(`${endpoint(kind)}/${entry.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});}
        else{if(!file.files[0])throw new Error('Choose an image first');const body=new FormData();body.append('metadata',JSON.stringify(data));body.append('image',file.files[0]);saved=await request(endpoint(kind),{method:'POST',body});}
        onSaved(saved);dialog.close();
    }catch(e){error.textContent=e.message;}finally{save.disabled=false;}};
    dialog.addEventListener('close',()=>{if(objectURL)URL.revokeObjectURL(objectURL);dialog.remove();},{once:true});dialog.append(form);document.body.append(dialog);dialog.showModal();
}

async function browse(kind,current,select){
    const dialog=el('dialog','moss-wardrobe-dialog moss-studio-library');dialog.setAttribute('aria-label',kind==='faces'?'Choose face':'Choose outfit');
    const header=el('header');header.append(el('h2','',kind==='faces'?'Choose a face':'Choose an outfit'));const add=el('button','',kind==='faces'?'Add my face':'Add my outfit');const close=el('button','','Close');close.onclick=()=>dialog.close();header.append(add,close);
    const controls=el('div','moss-wardrobe-controls');const search=el('input');search.placeholder=kind==='faces'?'Search face features or hairstyle':'Search garment, color or material';search.setAttribute('aria-label','Search library');const scope=el('select');scope.setAttribute('aria-label','Library source');for(const [value,label]of[['all','All items'],['user','My library']]){const option=el('option','',label);option.value=value;scope.append(option);}const category=el('select');category.setAttribute('aria-label','Library category');controls.append(search,scope,category);const reset=el('button','','Clear filters');reset.onclick=()=>{search.value='';scope.value='all';category.value='';activeTags.clear();filters.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed','false'));page=0;render();};controls.append(reset);
    const filters=el('div','moss-studio-tags');const status=el('p','moss-wardrobe-status');status.setAttribute('role','status');const grid=el('div','moss-wardrobe-grid');
    const footer=el('footer');const previous=el('button','','Previous page'),next=el('button','','Next page'),undo=el('button','','Undo remove');undo.hidden=true;footer.append(previous,undo,next);
    let entries=[],page=0,removed=null;const activeTags=new Set();
    async function reload(){try{entries=(await request(endpoint(kind))).entries;category.replaceChildren();for(const name of ['',...new Set(entries.map(e=>e.category))]){const option=el('option','',name||'All categories');option.value=name;category.append(option);}filters.replaceChildren();const tags=kind==='faces'?['Short','Medium','Long','Bob','Wavy','Straight','Layered','Oval','Round']:['Dress','Skirt','Coat','Knit','Lace','Satin','Mint','Pink','Black','White'];for(const tag of tags){const b=el('button','moss-wardrobe-chip',tag);b.setAttribute('aria-pressed',String(activeTags.has(tag)));b.onclick=()=>{activeTags.has(tag)?activeTags.delete(tag):activeTags.add(tag);filters.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(activeTags.has(x.textContent))));page=0;render();};filters.append(b);}render();}catch(e){status.textContent=e.message;}}
    function render(){const words=search.value.toLowerCase().trim().split(/\s+/).filter(Boolean);const results=entries.filter(e=>(scope.value!=='user'||e.editable)&&(!category.value||e.category===category.value)&&([...activeTags].every(tag=>(e.tags||[]).some(t=>t.toLowerCase()===tag.toLowerCase())))&&words.every(w=>`${e.label} ${e.tags} ${e.description} ${e.portrait_description||''} ${e.hair_description||''} ${e.hair_color||''} ${e.expression_description||''}`.toLowerCase().includes(w)));const pages=Math.max(1,Math.ceil(results.length/40));page=Math.min(page,pages-1);status.textContent=`${results.length} items · Page ${page+1} of ${pages}`;grid.replaceChildren();for(const entry of results.slice(page*40,(page+1)*40)){
        const card=el('div','moss-studio-card');const button=el('button','moss-wardrobe-outfit');button.setAttribute('aria-label',`Use ${entry.label}`);button.setAttribute('aria-pressed',String(entry.id===current));const image=el('img');image.src=thumb(kind,entry.id);image.alt=entry.label;image.loading='lazy';button.append(image,el('strong','',entry.label));const tags=el('div','moss-wardrobe-card-tags');for(const tag of (entry.tags||[]).slice(0,5))tags.append(el('span','',tag));button.append(tags);button.onclick=()=>{select(entry.id);dialog.close();};card.append(button);
        if(entry.editable){const row=el('div','moss-studio-actions');const edit=el('button','','Edit'),remove=el('button','','Remove');edit.onclick=()=>editAsset(kind,entry,async()=>{await reload();if(entry.id===current)select(entry.id);});remove.onclick=async()=>{try{await request(`${endpoint(kind)}/${entry.id}`,{method:'DELETE'});removed=entry.id;undo.hidden=false;await reload();}catch(e){status.textContent=e.message;}};row.append(edit,remove);card.append(row);}grid.append(card);
    }previous.disabled=page===0;next.disabled=page+1>=pages;grid.scrollTop=0;}
    search.oninput=scope.onchange=category.onchange=()=>{page=0;render();};previous.onclick=()=>{page--;render();};next.onclick=()=>{page++;render();};add.onclick=()=>editAsset(kind,null,async saved=>{scope.value='user';search.value='';activeTags.clear();await reload();select(saved.id);});undo.onclick=async()=>{try{await request(`${endpoint(kind)}/${removed}/restore`,{method:'POST'});undo.hidden=true;await reload();}catch(e){status.textContent=e.message;}};
    dialog.append(header,controls,filters,status,grid,footer);dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();await reload();search.focus();
}

function attach(node,kind,key){
    const selected=node.widgets.find(w=>w.name===key);if(!selected||node.mossStudioRefresh)return;
    selected.type='converted-widget';selected.hidden=true;selected.draw=()=>{};selected.computeSize=()=>[0,-4];
    const detailKey=kind==='faces'?'description_override':'extra_outfit_details';
    const detailWidget=node.widgets.find(w=>w.name===detailKey);
    if(detailWidget){detailWidget.type='converted-widget';detailWidget.hidden=true;detailWidget.draw=()=>{};detailWidget.computeSize=()=>[0,-4];}
    const root=el('div','moss-wardrobe-preview');const image=el('img','moss-studio-selected');const label=el('strong');const description=el('p');const row=el('div','moss-studio-actions');const choose=el('button','',kind==='faces'?'Choose face':'Choose outfit'),add=el('button','','Add my own');row.append(choose,add);root.append(image,label,description,row);
    const advanced=el('details','moss-studio-advanced');const summary=el('summary','',kind==='faces'?'Optional facial geometry override':'Additional outfit details');const detailsInput=el('textarea');detailsInput.setAttribute('aria-label',kind==='faces'?'Optional facial geometry override':'Additional outfit details');detailsInput.value=detailWidget?.value||'';detailsInput.oninput=()=>{if(detailWidget){detailWidget.value=detailsInput.value;detailWidget.callback?.(detailsInput.value);node.graph?.change();}};advanced.append(summary,detailsInput);if(kind==='outfits'){summary.textContent='Legacy unscoped note — clear before running';advanced.hidden=!detailsInput.value;}root.append(advanced);root.addEventListener('pointerdown',e=>e.stopPropagation());let ticket=0;
    async function refresh(){const n=++ticket;try{const entries=(await request(endpoint(kind))).entries;if(n!==ticket)return;const entry=entries.find(e=>e.id===selected.value);if(!entry)throw new Error('Choose an item from the library');label.textContent=entry.label;const referenceMode=kind==='faces'&&node.graph?._nodes.some(n=>n.comfyClass==='MOSSCharacterCardComposer'&&n.widgets?.find(w=>w.name==='reference_identity')?.value);advanced.hidden=kind==='faces'?Boolean(referenceMode):!detailsInput.value;const grouped=kind==='faces'&&node.graph?._nodes.some(n=>(n.comfyClass||n.type)==='MOSSRegionalGroupPlan');const isolated=kind==='faces'&&node.graph?._nodes.some(n=>(n.comfyClass||n.type)==='MOSSRegionalSampler');const locked=kind==='faces'&&node.graph?._nodes.some(n=>(n.comfyClass||n.type)==='MOSSCardPortraitSetup');description.textContent=grouped?'The reference guides the portrait. The three body views share the body settings and are generated together.':isolated?'The reference guides this portrait region only. All subject pixels are generated; the original face is not pasted or frozen. Other regions use independent conditions.':locked?'The reviewed face box protects identity and expression. Clothing edits affect its surroundings. For a personal upload, draw the protection box before sampling.':referenceMode?'Reference image supplies facial identity. Appearance controls inherit from this reference unless explicitly changed.':entry.description;image.src=thumb(kind,entry.id);image.alt=entry.label;}catch(e){label.textContent='Select a library item';description.textContent=e.message;}}
    function select(id){if(kind==='faces'&&detailWidget){detailWidget.value='';detailsInput.value='';}selected.value=id;selected.callback?.(id);node.graph?.change();node.setDirtyCanvas(true,true);}
    choose.onclick=()=>browse(kind,selected.value,select);add.onclick=()=>editAsset(kind,null,entry=>select(entry.id));image.onclick=choose.onclick;
    const callback=selected.callback;selected.callback=function(...args){callback?.apply(this,args);refresh();};const old=node.onConfigure;node.onConfigure=function(...args){old?.apply(this,args);detailsInput.value=detailWidget?.value||'';refresh();};const widget=node.addDOMWidget('library_preview','custom',root,{serialize:false,hideOnZoom:false,getHeight:()=>430});widget.computeSize=w=>[w,430];node.mossStudioRefresh=refresh;node.setSize([440,540]);refresh();
}

function formatPromptPreview(node){
    if(node.comfyClass!=='PreviewAny'||node.mossPromptPreview)return;
    const previous=node.onExecuted;
    node.onExecuted=function(message){
        let display=message;
        try{const value=JSON.parse(message.text?.[0]);if(value.bbox_format==='yxyx'&&Array.isArray(value.items))display={...message,text:[JSON.stringify(value,null,2)]};}catch{}
        return previous?.call(this,display);
    };
    node.mossPromptPreview=true;
}

function configureAgeMode(node) {
    const mode=node.widgets.find(w=>w.name==='age_mode');
    const age=node.widgets.find(w=>w.name==='age');
    if(!mode||!age)return;
    if(Array.isArray(mode.options?.values))
        mode.options.values=mode.options.values.filter(value=>value!=='From face selection');
    const sync=()=>{
        if(mode.value==='From face selection')mode.value='Unspecified adult age';
        age.disabled=mode.value!=='Set age';
    };
    const callback=mode.callback;
    mode.callback=function(...args){callback?.apply(this,args);sync();};
    const configured=node.onConfigure;
    node.onConfigure=function(...args){configured?.apply(this,args);sync();};
    sync();
}

app.registerExtension({name:'Mio.MOSS.CharacterStudio',nodeCreated(node){if(node.comfyClass==='MOSSReferenceCharacterSettings'){for(const w of node.widgets||[])w.label=({body_shape:'Body shape',body_appearance:'Shared body appearance'})[w.name]||w.label;}if(node.comfyClass==='MOSSCharacterSettings'){configureAgeMode(node);for(const w of node.widgets){w.label=({age_mode:'Age prompt',age:'Custom age',presentation:'Presentation',body_shape:'Body shape',body_appearance:'Shared body appearance',hair_style:'Hairstyle',hair_color:'Hair color',expression:'Expression',extra_character_details:'Additional portrait details'})[w.name]||w.label;}}if(node.comfyClass==='MOSSFaceLibrary')attach(node,'faces','face_id');if(node.comfyClass==='MOSSOutfitLibrary')attach(node,'outfits','outfit_id');if(node.comfyClass==='MOSSCharacterCardComposer'){for(const field of node.widgets){field.label=({long_edge:'Canvas width',short_edge:'Canvas height',privacy_blocks:'Privacy coverage',lighting:'Lighting'})[field.name]||field.label;}const w=node.widgets.find(w=>w.name==='reference_identity');if(w){w.type='converted-widget';w.hidden=true;w.draw=()=>{};w.computeSize=()=>[0,-4];}}},loadedGraphNode(node){node.mossStudioRefresh?.();formatPromptPreview(node);},afterConfigureGraph(){for(const n of app.graph._nodes)n.mossStudioRefresh?.();}});
