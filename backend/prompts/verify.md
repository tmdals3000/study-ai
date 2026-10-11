<source>
{{SOURCE}}
</source>

아래 각 claim이 위 source만으로 뒷받침되는지 엄격하게 판정하라. 너의 사전 지식으로 볼 때 맞는 내용이라도 source에 없으면 뒷받침되지 않은 것이다.

claim에 cites 속성이 있으면 source 중 그 id의 note만 근거로 인정한다. 다른 note에만 있는 내용은 source 어딘가에 있더라도 뒷받침되지 않은 것으로 판정한다.

{{CLAIMS}}

각 claim에 대해:
- id: claim의 id
- verdict:
  - supported: 모든 문장이 source에 명시되어 있거나 source에서 직접 도출된다.
  - partial: 일부 문장·구절이 source에 없다 (덧붙인 예시, 이유, 수치, 일반화, 과장, 비유 등).
  - unsupported: 핵심 내용이 source에 없거나 source와 모순된다.
- issues: partial·unsupported일 때 무엇이 근거가 없는지 짧게. supported면 빈 문자열.
- corrected: partial일 때만, 원래 설명 본문(제목 제외)에서 근거 없는 부분만 삭제한 버전. 새 내용을 추가하거나 다시 쓰지 않는다. 그 외에는 빈 문자열.

모든 claim id에 대해 빠짐없이 판정한다.
