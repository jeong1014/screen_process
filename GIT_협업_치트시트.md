# Git 협업 치트시트 (브랜치 + PR)

두 명이 같은 저장소에서 부딪히지 않고 작업하는 방법.
핵심 규칙: **main에 직접 작업하지 말고, 각자 브랜치에서 작업한 뒤 PR로 합친다.**

---

## 매번 반복하는 작업 사이클

### 1. 작업 시작 전 — 최신 main 받기
```bash
git checkout main
git pull
```

### 2. 내 작업용 브랜치 만들기
```bash
git checkout -b feature/작업이름
```
예시 이름: `feature/label-fix`, `feature/monitor-ui`, `fix/print-bug`
(동료는 다른 이름으로 자기 브랜치를 만든다)

### 3. 작업하고 저장(commit)
```bash
git add .
git commit -m "무엇을 했는지 한 줄 설명"
```
작은 단위로 자주 커밋하는 게 좋다.

### 4. GitHub에 올리기(push)
```bash
git push -u origin feature/작업이름
```
처음 한 번만 `-u origin ...`, 그다음부터는 그냥 `git push`

### 5. GitHub에서 Pull Request(PR) 열기
- push 후 GitHub가 보여주는 **"Compare & pull request"** 버튼 클릭
- 제목/설명 적고 PR 생성
- 동료가 확인 후 **Merge** → main에 반영됨

### 6. 합친 뒤 정리
```bash
git checkout main
git pull                       # 방금 합친 내용 받기
git branch -d feature/작업이름   # 끝난 브랜치 삭제
```
→ 다음 작업은 다시 1번부터.

---

## 충돌(conflict)을 줄이는 법

1. **파일/영역을 나눠서 작업**
   - 예: 한 명은 `app.py`, `print_templates.py` (백엔드)
   - 다른 한 명은 `frontend/` (화면)
2. **브랜치는 짧게** — 하루 이틀 안에 끝내고 합치기
3. **작업 전 항상 `git pull`**, 끝나면 바로 push

---

## 자주 쓰는 명령어

| 상황 | 명령어 |
|------|--------|
| 지금 어느 브랜치인지 확인 | `git branch` |
| 브랜치 이동 | `git checkout 브랜치이름` |
| 변경된 파일 확인 | `git status` |
| 원격의 최신 브랜치 목록 받기 | `git fetch` |
| 커밋 기록 보기 | `git log --oneline` |

---

## 충돌이 났을 때 (Merge conflict)

당황하지 말 것. main을 내 브랜치로 당길 때 충돌이 나면:
```bash
git checkout feature/작업이름
git pull origin main        # 여기서 충돌 발생 가능
```
- 충돌난 파일을 열면 `<<<<<<<`, `=======`, `>>>>>>>` 표시가 있다.
- 그 사이에서 **남길 코드만 남기고** 표시 줄들은 지운다.
- 정리 후:
```bash
git add .
git commit -m "conflict 해결"
git push
```
