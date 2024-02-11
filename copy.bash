#!/bin/bash
#
function get_mount_point()
{
   MOUNT_POINT=
   for i in $(df); do
     if [[ $i  =~ "CIRCUITPY" ]]; then
       MOUNT_POINT="$i"
     fi
   done
}
function copy_updated_files()
{
  if [[ ! $1 =~ "/lib/" ]]; then
    local from=$1
    local to="$MOUNT_POINT/${from/\.\//}"
    # echo "from                     $from ($(date -r $from))"
    # echo "to   $to ($(date -r $to))"
    # echo "****"
    if [ "$to" -ot "$from" ]; then
      ((++COUNTER))
      #echo "cp $from $to"
      cp -fv "$from" "$to"
    elif [[ "$to" > "$from" ]]; then
      echo "$(ls -la $from $to)"
    fi
  fi
}

clear
get_mount_point
if [[ -n "$MOUNT_POINT" ]]; then
  echo "CIRCUITPY mounted at $MOUNT_POINT"
  COUNTER=0
  while IFS= read -r file; do
    ((++COUNTER))
    copy_updated_files "$file"
  done < <(find . -type f -name "*.py")
  echo "$COUNTER files copied"
else
  echo "CIRCUITPY not mounted"
fi
