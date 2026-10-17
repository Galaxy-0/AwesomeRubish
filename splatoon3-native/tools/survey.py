# Run nxnative's survey on Splatoon 3 (base XCI + update NSP) without the NSP-folder scan.
import sys, os, pathlib
R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'upstream/scripts'))
import build_ipa_from_nsp as B
sys.path.insert(0, str(R / 'upstream/dm/tools')); import nacp; B.nacp = nacp
D = pathlib.Path(os.environ.get('SPL3_DIR', '/Users/galaxy/Downloads/喷射战士3'))
fam = {'base': D / 'xci本体/Splatoon 3 [0100C2500FC20000][v0].xci',
       'updates': [(720896, D / 'upd-v11.3.0/[UPD][11.3.0][0100C2500FC20800][US][22.5.0].nsp')], 'dlc': []}
os.environ['DOTNET_ROOT'] = '/opt/homebrew/opt/dotnet@9/libexec'; env = dict(os.environ, DOTNET_ROOT='/opt/homebrew/opt/dotnet@9/libexec')
out = R / 'work'
B.survey(out, 0x0100C2500FC20000, fam, R.parent / 'splatoon3-decomp/tools/keys/prod.keys.clean', R / 'upstream', sys.executable, env)
