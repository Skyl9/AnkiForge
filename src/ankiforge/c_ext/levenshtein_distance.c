#include <string.h>
#include <stdlib.h>

#define MIN3(a, b, c) ((a) < (b) ? ((a) < (c) ? (a) : (c)) : ((b) < (c) ? (b) : (c)))

#if defined(_WIN32) || defined(_WIN64)
    __declspec(dllexport) double calculate_similarity(const char *s1, const char *s2)
#else
    double calculate_similarity(const char *s1, const char *s2)
#endif
{
    // SÉCURITÉ 1 : Protection contre les pointeurs nuls venant de Python
    if (!s1 || !s2) return 0.0;

    int len1 = strlen(s1);
    int len2 = strlen(s2);

    if (len1 == 0 && len2 == 0) return 1.0;
    if (len1 == 0 || len2 == 0) return 0.0;

    int *column = (int *)malloc((len1 + 1) * sizeof(int));

    // SÉCURITÉ 2 : Protection contre l'échec d'allocation mémoire
    if (!column) return 0.0;

    for (int i = 0; i <= len1; i++) {
        column[i] = i;
    }

    for (int x = 1; x <= len2; x++) {
        column[0] = x;
        int last_diagonal = x - 1;
        for (int y = 1; y <= len1; y++) {
            int old_diagonal = column[y];
            column[y] = MIN3(
                column[y] + 1,
                column[y - 1] + 1,
                last_diagonal + (s1[y - 1] == s2[x - 1] ? 0 : 1)
            );
            last_diagonal = old_diagonal;
        }
    }

    int distance = column[len1];
    free(column);

    int max_len = len1 > len2 ? len1 : len2;
    return 1.0 - ((double)distance / (double)max_len);
}