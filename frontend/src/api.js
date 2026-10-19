const token=location.hash.slice(1);
export async function api(path,body){
  const response=await fetch('/api/'+path,{headers:{'X-Campus-Token':token,...(body?{'Content-Type':'application/json'}:{})},method:body?'POST':'GET',body:body?JSON.stringify(body):undefined});
  const value=await response.json();if(!response.ok)throw Error(value.error||'请求失败');return value;
}
