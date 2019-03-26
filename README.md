# vmrunner
Utility for booting [IncludeOS](https://github.com/includeos/includeos) binaries

### Configure Settings

```
  conan config install https://github.com/includeos/conan_config.git
```

##### View remote and profiles installed

* Remotes:
```
  conan remote list
```
You should have these:

```
  includeos: https://api.bintray.com/conan/includeos/includeos [Verify SSL: True]
  includeos-test: https://api.bintray.com/conan/includeos/test-packages [Verify SSL: True]
```

* Profiles:

```
  conan profile list
```


### Build and run vmrunner

```bash
  mkdir build
  cd build
  conan create .. includeos/stable -pr <profile-name>
```
