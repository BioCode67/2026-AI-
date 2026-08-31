# -*- coding: utf-8 -*-
"""
PPTX → PDF 변환 (LibreOffice UNO)

`soffice --convert-to pdf` 를 그냥 쓰면 한글과 문장부호 사이에 자동 자간이 들어가
"바라며 ," 처럼 부호 앞에 공백이 생긴다. 이는 LibreOffice 의 한중일 자동 자간
(ParaIsCharacterDistance) 때문이므로, 문서를 연 뒤 모든 문단에서 이 옵션을 끄고
PDF 로 내보낸다.

사용법:  python3 tools/pptx_to_pdf.py <입력.pptx> <출력.pdf>
"""
import os, sys, subprocess, time, uno
from pathlib import Path
from com.sun.star.beans import PropertyValue


def prop(name, value):
    p = PropertyValue(); p.Name = name; p.Value = value
    return p


def connect(port=2002, tries=40):
    ctx = uno.getComponentContext()
    resolver = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", ctx)
    url = f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext"
    for _ in range(tries):
        try:
            return resolver.resolve(url)
        except Exception:
            time.sleep(0.75)
    raise RuntimeError("LibreOffice 에 연결하지 못했습니다.")


def kill_cjk_spacing(doc):
    """모든 도형의 모든 문단에서 한중일 자동 자간을 끈다."""
    touched = 0

    def walk(shape):
        """그룹 도형 안쪽까지 재귀로 내려간다."""
        nonlocal touched
        try:                                  # 그룹이면 자식으로 내려감
            if shape.supportsService("com.sun.star.drawing.GroupShape"):
                for i in range(shape.getCount()):
                    walk(shape.getByIndex(i))
                return
        except Exception:
            pass
        try:                                  # 표는 셀 단위로
            if shape.supportsService("com.sun.star.drawing.TableShape"):
                tbl = shape.Model
                for r in range(tbl.getRowDescriptions().getCount()):
                    for c in range(tbl.getColumnDescriptions().getCount()):
                        _paras(tbl.getCellByPosition(c, r))
                return
        except Exception:
            pass
        _paras(shape)

    def _paras(obj):
        nonlocal touched
        try:
            enum = obj.Text.createEnumeration()
        except Exception:
            try:
                enum = obj.createEnumeration()
            except Exception:
                return
        while enum.hasMoreElements():
            para = enum.nextElement()
            for name, val in (("ParaIsCharacterDistance", False),
                              ("ParaIsForbiddenRules", False),
                              ("ParaIsHangingPunctuation", False)):
                try:
                    para.setPropertyValue(name, val); touched += 1
                except Exception:
                    pass

    for page in doc.getDrawPages():
        for i in range(page.getCount()):
            walk(page.getByIndex(i))
    return touched


def main():
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve()
    profile = Path("/tmp/lo_profile_pdf")
    port = 2002
    proc = subprocess.Popen([
        "soffice", "--headless", "--invisible", "--nologo", "--nofirststartwizard",
        "--norestore", f"-env:UserInstallation=file://{profile}",
        f"--accept=socket,host=127.0.0.1,port={port};urp;"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ctx = connect(port)
        desktop = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx)
        doc = desktop.loadComponentFromURL(
            uno.systemPathToFileUrl(str(src)), "_blank", 0,
            (prop("Hidden", True), prop("ReadOnly", False)))
        n = kill_cjk_spacing(doc)
        doc.storeToURL(uno.systemPathToFileUrl(str(dst)),
                       (prop("FilterName", "impress_pdf_Export"),))
        doc.close(False)
        print(f"변환 완료: {dst.name}  (문단 속성 {n}건 조정)")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
