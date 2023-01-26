function [pvals, Fstats, dfs] = GRStest_p(results)

% warning off;
% Take output from ts_regs_full (for example) and run a GRS test
% Give the statistic and the df needed to test it
pvals = ones(2,1);
df = zeros(2, 2);
stats = ones(2,1);

nPtfs=size(results.pret,2)-1;
nMonths=sum(isfinite(results.pret(:,1)));
nFactors=results.nFactors;

% Calculate the GRS stat for the full model %

% Get the degrees of freedom
df(1,:) = [nPtfs, nMonths - nPtfs - nFactors];

indFinite = isfinite(sum(results.pret,2)) & isfinite(sum([results.factorLoadings.factor],2)); 

% Calculate the numerator
numer = results.alpha(1:nPtfs)'*cov(results.resid(indFinite,1:nPtfs))^(-1)*results.alpha(1:nPtfs);
numer = numer/100^2; %correct for percentage return multiplication

% Calculate the denominator
f_mat = [];
for i = 1:nFactors
    f_mat = [f_mat, results.factorLoadings(i).factor(indFinite)] ;
end
Ef = nanmean(f_mat,1)';
denom = 1 + Ef'*cov(f_mat)^(-1)*Ef;

% The statistic
stats(1) = df(1,2)/df(1,1) * numer/denom;

pvals(1) = 1 - fcdf(stats(1), df(1,1), df(1,2));


% Calculate the GRS stat for the reduced model %

b=[results.factorLoadings.b]';
b=b(:,1:nPtfs);
x=[results.factorLoadings.factor];
x=x(indFinite,:);
a=repmat(results.alpha(1:nPtfs)',sum(indFinite),1)/100;
resid=results.resid(indFinite,1:nPtfs);

resxret=x*b+a+resid;


numer = results.xret(1:nPtfs)'*cov(resxret)^(-1)*results.xret(1:nPtfs);
numer = numer/100^2; %correct for percentage return multiplication
denom = 1;
df(2,:) = [nPtfs, nMonths - nPtfs];
stats(2) = df(2,2)/df(2,1) * numer/denom;

pvals(2) = 1 - fcdf(stats(2), df(2,1), df(2,2));

if nargout == 3
    Fstats = stats;
    dfs = df;
end

% warning on;
