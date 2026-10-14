# 하츠네 미쿠 — SVG와 전체 제작 과정

**[웹에서 보기](https://legerdo.github.io/hatsune-miku-svg-process/) · [전체 과정 영상](https://legerdo.github.io/hatsune-miku-svg-process/hatsune-miku-process.mp4) · [SVG 원본](https://legerdo.github.io/hatsune-miku-svg-process/hatsune-miku.svg) · [전체 ZIP](https://legerdo.github.io/hatsune-miku-svg-process/hatsune-miku-complete.zip)**


공식 KEI 전신 일러스트를 참고하여 만든 순수 벡터 SVG와, 스케치부터 완성까지 모든 제작 배치를 재생하는 애니메이션입니다.

## 열기

- `output/miku-drawing-player.html`: Chrome에서 직접 열 수 있는 독립형 재생기. 인터넷 연결이나 서버가 필요하지 않습니다. 재생·일시정지, 처음부터, 구간 탐색, 단계 선택, 속도 조절, 얼굴·소매 확대를 지원합니다.
- `output/hatsune-miku-process.mp4`: 전체 과정 H.264 영상. 최종 인코딩 결과는 함께 제공하는 검증 JSON에 기록됩니다.
- `output/hatsune-miku.svg`: 완성된 편집 가능한 SVG. 실제 그리기 요소는 정확히 1,600개의 `<path>`입니다.
- `output/hatsune-miku.png`: SVG를 Chromium으로 렌더링한 2,076×3,164 미리보기입니다.

## 제작 과정과 요소 수

12개 제작 배치마다 렌더링된 화면을 확인하고 다음 작업을 결정했습니다. 각 배치의 판단 기록과 SVG·PNG 체크포인트를 보존했습니다.

1. 움직임과 비례를 잡는 스케치
2. 실루엣과 내부 구조선
3. 큰 색면과 밑색
4. 색면 연결과 밝기 관계
5. 얼굴과 손의 구조
6. 빛과 그림자, 전체 입체감
7. 눈·얼굴·헤드셋 정교화
8. 옷 주름·소매 장치·손끝
9. 왼쪽 트윈테일의 흐름과 세부 음영
10. 오른쪽 트윈테일의 빛과 색 변화
11. 부츠의 주름·봉제선·반사광
12. 전체 점검과 밑그림·밑칠 정리

완성 SVG의 1,600개 패스는 실제 색면과 윤곽입니다. 숨긴 요소, 빈 경로, 외부 이미지, 내장 비트맵으로 수량을 맞추지 않았습니다. 하나의 패스에는 공간적으로 가까운 같은 색의 여러 하위 윤곽이 들어갈 수 있습니다. 원본의 50,363개 연결 색 영역을 이 방식으로 보존했습니다. 따라서 1,600개는 SVG의 그리기 요소 수이며, 단일 연속 붓질이나 모든 하위 경로의 수를 뜻하지 않습니다.

과정 재생에는 최종 패스 외에 스케치 71획과 밑칠 722개가 포함됩니다. 전체 2,393개 그리기 동작(스케치 71 + 채색 2,322)을 기록 순서대로 재생합니다. 밑그림은 채색 중 점진적으로 사라지고, 마지막에는 초기 밑칠 레이어를 2초에 걸쳐 제거합니다. 최종 정지 화면에는 1,600개 완성 패스만 남습니다.

영상은 실제 인간이 펜을 움직이는 실시간 촬영이 아니라, 이번 작업의 단계별 SVG 기록을 바탕으로 구성한 **드로잉 시뮬레이션을 실제 브라우저에서 녹화한 것**입니다. 선을 점진적으로 긋고 개별 색면을 채우며, 배치 사이에 확인 시간을 둡니다. 단계 설명과 확대 창도 영상에 포함됩니다.

## 원본과 사용 조건

- 원작: KEI의 공식 하츠네 미쿠 일러스트
- 출처 페이지: https://piapro.net/intl/en_character.html
- 선택한 이미지: https://piapro.net/intl/images/ch_img_miku.png
- 원본 크기: 519×791
- 권리 표시: Hatsune Miku © Crypton Future Media, INC. 2007
- 원본 라이선스: Creative Commons Attribution-NonCommercial 3.0 Unported (CC BY-NC 3.0)
- 라이선스: https://creativecommons.org/licenses/by-nc/3.0/
- 공식 안내: https://piapro.net/intl/en_for_creators.html

이 결과물은 위 일러스트를 벡터화하고 제작 과정을 재구성한 변형입니다. 원본의 출처 표시 및 비상업적 이용 조건을 유지합니다. 제공된 출처 정보는 `reference/source.json`과 SVG 메타데이터에도 들어 있습니다.

## 검증 및 재현

작업 환경은 Windows 11, Python 3.13, 설치된 Chrome, NumPy/OpenCV/SciPy/Pillow/Playwright, FFmpeg입니다. 폰트 파일이나 외부 JavaScript 라이브러리는 결과물에 포함되지 않습니다.

프로젝트 폴더에서 PowerShell로 실행합니다. 이미 저장된 `recording/session.json`을 그대로 사용하면 벡터 결과와 재생기를 다시 만들 수 있습니다.

```powershell
$env:PATH += ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
python studio.py final
python build_player.py --duration 292
python validate_artifacts.py
python verify_player.py
```

전체 영상을 다시 녹화하려면 다음을 실행합니다. 영상 파일이 이미 있을 때에는 실수로 덮어쓰지 않도록 중단합니다. 기존 결과를 의도적으로 교체하는 경우에만 `--overwrite`를 추가합니다.

```powershell
python record_video.py --html output/miku-drawing-player.html --output output/hatsune-miku-process.mp4 --expect-paths 1600 --expect-underpainting 722 --fps 24
python validate_artifacts.py --video output/hatsune-miku-process.mp4
```

검증 파일:

- `output/validation.json`: 실제 SVG XML·요소 수·외부 리소스·파일 해시·영상 메타데이터 검사
- `output/player-verification.json`: 재생기의 실제 입력, 탐색, 확대, 마지막 상태와 오프라인 실행 검사
- `output/hatsune-miku-process.report.json`: 실제 녹화 청크·최종 동작 수·FFmpeg 종료 상태
- `output/video-verification.json`: 전체 영상 디코딩, 주요 프레임, 별도 재생기 렌더와 영상 마지막 프레임 비교
- `recording/prime-qa/`: 별도 검증에서 얻은 주요 프레임과 상세 기록
- `checkpoints/`: 제작 도중 확인한 각 배치의 SVG와 PNG

세부 색 영역을 보존하므로 SVG와 HTML 파일의 크기는 각각 약 19 MB와 20 MB입니다. 원본보다 확대했을 때 새로운 세부를 임의로 만들어 내는 방식은 사용하지 않았습니다.

## GitHub Pages

`main` 브랜치의 변경은 `.github/workflows/pages.yml`에서 SVG 요소 수, 산출물 해시, 필수 파일과 사이트 링크를 검사한 뒤 `output/`을 Pages에 배포합니다. 영상과 재생기를 다시 생성하는 작업은 위 Windows 재현 절차를 사용합니다.
