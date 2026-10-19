from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
out=root/'dist';out.mkdir(exist_ok=True)
target=out/'oppo-ai-pin-campus.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
    for name in ('LICENSE','THIRD-PARTY-NOTICES.txt','plugin.json','mcp.json','.mcp.json','.codex-plugin','skills','runtime','ui','references','assets/icon.png','assets/icon.jpg'):
        p=root/name
        for f in ([p] if p.is_file() else p.rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc': z.write(f,f.relative_to(root))
print(target)
