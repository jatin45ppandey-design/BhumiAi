export function Status({value}:{value:string}){return <span className={'status '+value}>{value.replace('_',' ')}</span>}
