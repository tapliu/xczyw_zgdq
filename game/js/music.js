const MusicManager = {
  _current: null,
  _scene: null,
  _enabled: true,
  _volume: 0.4,
  _battleIndex: -1,

  _tracks: {
    menu: { src: '/music/bgm_menu_01.m4a', loop: true },
    draw: { src: '/music/bgm_menu_02.m4a', loop: true },
    place: { src: '/music/bgm_place_01.m4a', loop: true },
    battle: [
      { src: '/music/bgm_battle_01.m4a' },
      { src: '/music/bgm_battle_02.m4a' },
      { src: '/music/bgm_battle_03.m4a' },
      { src: '/music/bgm_battle_04.m4a' },
      { src: '/music/bgm_battle_05.m4a' },
      { src: '/music/bgm_battle_06.m4a' },
    ],
    victory: { src: '/music/bgm_battle_04.m4a', loop: false },
    defeat: { src: '/music/bgm_menu_02.m4a', loop: false },
  },

  _nextBattle() {
    const list = this._tracks.battle;
    let idx;
    do {
      idx = Math.floor(Math.random() * list.length);
    } while (idx === this._battleIndex && list.length > 1);
    this._battleIndex = idx;
    return list[idx];
  },

  play(scene) {
    if (scene === this._scene && this._current && !this._current.paused) return;
    this._scene = scene;
    if (!this._enabled) return;
    this.stop();

    const track = scene === 'battle' ? this._nextBattle() : this._tracks[scene];
    if (!track) return;

    const audio = new Audio(track.src);
    audio.volume = this._volume;
    audio.loop = track.loop !== false;
    audio.addEventListener('ended', () => {
      if (scene === 'battle') this.play('battle');
    });
    audio.play().catch(() => {});
    this._current = audio;
  },

  stop() {
    if (this._current) {
      this._current.pause();
      this._current.src = '';
      this._current = null;
    }
    this._battleIndex = -1;
  },

  setVolume(v) {
    this._volume = Math.max(0, Math.min(1, v));
    if (this._current) this._current.volume = this._volume;
  },

  toggle() {
    this._enabled = !this._enabled;
    if (this._enabled) {
      if (this._scene) this.play(this._scene);
    } else {
      this.stop();
    }
    return this._enabled;
  },

  isEnabled() { return this._enabled; },
  getVolume() { return this._volume; },
};
