from pathlib import Path
import stat
import zipfile

import pytest
from scripts.install_private_archive import install


def package(path, extra=None):
    with zipfile.ZipFile(path,'w') as z:
        for name,value in {'site/index.html':'<html>fixture</html>', 'site/assets/app.js':'// fixture', 'site/data/manifest.json':'{}'}.items():
            z.writestr(name,value)
        if extra:
            z.writestr(*extra)


def test_extracts_real_tree_and_never_overwrites(tmp_path):
    archive=tmp_path/'input.zip';package(archive)
    target=tmp_path/'site';install(archive,target)
    assert (target/'data/manifest.json').read_text()=='{}'
    assert (target/'assets/app.js').read_text()=='// fixture'
    with pytest.raises(FileExistsError):install(archive,target)


@pytest.mark.parametrize('name',['site/../escape.js','site/assets/extra.js','/site/index.html','site/data/.secret.json','site/assets/media/../../escape.png'])
def test_rejects_bad_members_before_writing(tmp_path,name):
    archive=tmp_path/'input.zip';package(archive,(name,'bad'))
    with pytest.raises(ValueError):install(archive,tmp_path/'site')
    assert not (tmp_path/'site').exists()
    assert not list(tmp_path.glob('.teaching-install-*'))


def test_rejects_zip_links_and_destination_links(tmp_path):
    archive=tmp_path/'input.zip'
    link=zipfile.ZipInfo('site/assets/media/link.png');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
    package(archive,(link,'/etc/passwd'))
    with pytest.raises(ValueError):install(archive,tmp_path/'site')
    package(archive)
    (tmp_path/'linked').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError):install(archive,tmp_path/'linked/site')
