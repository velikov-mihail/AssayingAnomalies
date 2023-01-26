function res = rowrank(mat,percentile,low2high)

% rowrank(mat):                       rank rows high to low
% rowrank(mat,0,1):                   rank rows low to high
% rowrank(mat,1):                     rank rows high to low, percentiles
% rowrank(mat,1,1):                   rank rows low to high, percentiles
% rowrank(mat,2):                     rank rows high to low, z-scores (invert cum norm)
% rowrank(mat,2,1):                   rank rows low to high, z-scores (invert cum norm)
% rowrank(mat,3):                     rank rows high to low, z-scores(x-mu)/sig
% rowrank(mat,3,1):                   rank rows low to high, z-scores(x-mu)/sig

if nargin == 3
    mat = -mat;
end

[r c] = size(mat);
if c <= 1
    disp(['Not a matrix']);
else
    temp = tiedrank(mat')';
    if nargin > 1
        if percentile > 0
            temp = (2*temp-1)./repmat(2*max(temp')',1,cols(temp));
        end
        if percentile == 2
            temp = norminv(temp);
        elseif percentile == 3
            M = nanmean(mat')';
            S = nanstd(mat')';
            temp = (mat - repmat(M,1,c))./repmat(S,1,c);
        end
    end
end

res = temp;
